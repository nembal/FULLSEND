"""FastAPI web adapter for the Fullsend communication service.

Provides HTTP endpoints for status, feed, and commands,
plus WebSocket support for real-time updates.
"""

import asyncio
import json
import logging
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..config import Settings
from ..core.bus import RedisBus, CHANNEL_FROM_AGENT
from ..core.messages import HumanMessage, HumanMessageType
from ..core.router import MessageRouter

# Template directory
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

logger = logging.getLogger(__name__)


class CommandRequest(BaseModel):
    """Request body for POST /api/command."""

    command: str
    args: dict[str, Any] | None = None
    user_id: str = "web_user"


class StatusResponse(BaseModel):
    """Response for GET /api/status."""

    status: str
    mode: str
    redis_connected: bool
    uptime_seconds: float
    timestamp: str


class FeedItem(BaseModel):
    """A single item in the activity feed."""

    id: str
    type: str
    content: str
    timestamp: str
    source: str


class FeedResponse(BaseModel):
    """Response for GET /api/feed."""

    items: list[FeedItem]
    count: int


class ConnectionManager:
    """Manages WebSocket connections for broadcasting messages."""

    def __init__(self) -> None:
        """Initialize the connection manager."""
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and track a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._connections.append(websocket)
        logger.info("WebSocket client connected. Total: %d", len(self._connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)
        logger.info("WebSocket client disconnected. Total: %d", len(self._connections))

    async def broadcast(self, message: str | dict[str, Any]) -> None:
        """Broadcast a message to all connected clients.

        Args:
            message: Message to send (string or dict, will be JSON serialized)
        """
        if isinstance(message, dict):
            message = json.dumps(message)

        async with self._lock:
            disconnected: list[WebSocket] = []
            for websocket in self._connections:
                try:
                    await websocket.send_text(message)
                except Exception:
                    disconnected.append(websocket)

            # Clean up disconnected clients
            for ws in disconnected:
                if ws in self._connections:
                    self._connections.remove(ws)
                    logger.info("Removed stale WebSocket. Total: %d", len(self._connections))

    @property
    def connection_count(self) -> int:
        """Get the number of connected clients."""
        return len(self._connections)


class WebAdapter:
    """FastAPI web adapter for HTTP-based communication."""

    def __init__(
        self,
        settings: Settings,
        redis_bus: RedisBus | None = None,
        message_router: MessageRouter | None = None,
    ) -> None:
        """Initialize the web adapter.

        Args:
            settings: Application settings
            redis_bus: Optional Redis bus for pub/sub
            message_router: Optional message router for centralized subscriptions
        """
        self.settings = settings
        self.redis_bus = redis_bus
        self.message_router = message_router
        self._connection_manager = ConnectionManager()
        self.app = self._create_app()
        self._start_time = datetime.utcnow()
        self._feed: deque[FeedItem] = deque(maxlen=100)
        self._paused = False
        self._redis_subscribed = False

    def _create_app(self) -> FastAPI:
        """Create and configure the FastAPI application."""
        app = FastAPI(
            title="Fullsend Communication Service",
            description="Web interface for the Fullsend GTM agent",
            version="0.1.0",
        )

        # Add CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Register routes
        self._register_routes(app)

        return app

    def _register_routes(self, app: FastAPI) -> None:
        """Register all API routes."""

        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket) -> None:
            """WebSocket endpoint for real-time updates.

            Clients connect here to receive live updates from Redis.
            """
            await self._connection_manager.connect(websocket)

            # Subscribe to Redis if not already subscribed
            await self._ensure_redis_subscription()

            try:
                # Keep connection alive and handle incoming messages
                while True:
                    try:
                        # Wait for client messages (ping/pong or commands)
                        data = await websocket.receive_text()
                        # Handle client messages if needed (e.g., ping)
                        if data == "ping":
                            await websocket.send_text("pong")
                    except WebSocketDisconnect:
                        break
            finally:
                await self._connection_manager.disconnect(websocket)

        @app.get("/", response_class=HTMLResponse)
        async def root() -> HTMLResponse:
            """Serve the dashboard HTML page."""
            dashboard_path = TEMPLATES_DIR / "dashboard.html"
            if dashboard_path.exists():
                return HTMLResponse(content=dashboard_path.read_text(), status_code=200)
            # Fallback to JSON if template not found
            return HTMLResponse(
                content="<html><body><h1>Fullsend Dashboard</h1><p>Template not found. <a href='/docs'>API Docs</a></p></body></html>",
                status_code=200,
            )

        @app.get("/api/info")
        async def api_info() -> dict[str, str]:
            """API info endpoint returning service metadata."""
            return {
                "service": "Fullsend Communication Service",
                "version": "0.1.0",
                "docs": "/docs",
            }

        @app.get("/api/status", response_model=StatusResponse)
        async def get_status() -> StatusResponse:
            """Get current service status."""
            now = datetime.utcnow()
            uptime = (now - self._start_time).total_seconds()

            return StatusResponse(
                status="paused" if self._paused else "running",
                mode=self.settings.env,
                redis_connected=self.redis_bus is not None and self.redis_bus._connected,
                uptime_seconds=uptime,
                timestamp=now.isoformat(),
            )

        @app.get("/api/feed", response_model=FeedResponse)
        async def get_feed() -> FeedResponse:
            """Get recent activity feed."""
            items = list(self._feed)
            return FeedResponse(items=items, count=len(items))

        @app.post("/api/command")
        async def post_command(request: CommandRequest) -> dict[str, Any]:
            """Execute a command.

            Supported commands:
            - pause: Pause the agent
            - go: Resume the agent
            - status: Get status (same as GET /api/status)
            - idea: Submit an idea (requires args.content)
            """
            command = request.command.lower()

            if command == "pause":
                self._paused = True
                logger.info(f"Agent paused by {request.user_id}")
                return {"success": True, "message": "Agent paused", "status": "paused"}

            elif command == "go":
                self._paused = False
                logger.info(f"Agent resumed by {request.user_id}")
                return {"success": True, "message": "Agent resumed", "status": "running"}

            elif command == "status":
                now = datetime.utcnow()
                uptime = (now - self._start_time).total_seconds()
                return {
                    "success": True,
                    "status": "paused" if self._paused else "running",
                    "mode": self.settings.env,
                    "redis_connected": self.redis_bus is not None and self.redis_bus._connected,
                    "uptime_seconds": uptime,
                }

            elif command == "idea":
                if not request.args or "content" not in request.args:
                    raise HTTPException(
                        status_code=400,
                        detail="idea command requires args.content",
                    )

                content = request.args["content"]

                # Create and publish HumanMessage
                message = HumanMessage(
                    type=HumanMessageType.IDEA_SUBMIT,
                    payload={
                        "content": content,
                        "source_channel": "web",
                        "submitted_by": request.user_id,
                    },
                    source="web",
                    user_id=request.user_id,
                )

                if self.redis_bus and self.redis_bus._connected:
                    from ..core.bus import publish_to_agent
                    await publish_to_agent(self.redis_bus, message)
                    logger.info(f"Idea submitted via web: {content[:50]}...")
                    return {
                        "success": True,
                        "message": "Idea submitted",
                        "content": content,
                    }
                else:
                    logger.warning(f"Idea submitted offline: {content[:50]}...")
                    return {
                        "success": True,
                        "message": "Idea submitted (offline mode)",
                        "content": content,
                        "offline": True,
                    }

            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown command: {command}. Supported: pause, go, status, idea",
                )

    def add_feed_item(
        self,
        item_id: str,
        item_type: str,
        content: str,
        source: str = "system",
    ) -> None:
        """Add an item to the activity feed.

        Args:
            item_id: Unique identifier for the item
            item_type: Type of item (e.g., status_update, action_request)
            content: Human-readable content
            source: Source of the item (discord/web/system)
        """
        feed_item = FeedItem(
            id=item_id,
            type=item_type,
            content=content,
            timestamp=datetime.utcnow().isoformat(),
            source=source,
        )
        self._feed.appendleft(feed_item)

    async def _ensure_redis_subscription(self) -> None:
        """Subscribe to Redis channel if not already subscribed.

        Uses message router if available, otherwise subscribes directly.
        """
        if self._redis_subscribed:
            return

        # Prefer using the message router
        if self.message_router:
            self.message_router.register_handler(self._handle_redis_message)
            self._redis_subscribed = True
            logger.info("WebAdapter registered with message router")
            return

        # Fallback: subscribe directly to Redis
        if self.redis_bus is None or not self.redis_bus.is_connected:
            logger.warning("Cannot subscribe to Redis: not connected")
            return

        try:
            await self.redis_bus.subscribe(CHANNEL_FROM_AGENT, self._handle_redis_message)
            self._redis_subscribed = True
            logger.info("WebAdapter subscribed to Redis channel: %s", CHANNEL_FROM_AGENT)
        except Exception as e:
            logger.error("Failed to subscribe to Redis: %s", e)

    async def init(self) -> None:
        """Initialize the web adapter.

        Call this after creating the adapter to set up Redis subscription
        before any WebSocket clients connect.
        """
        await self._ensure_redis_subscription()
        logger.info("WebAdapter initialized")

    async def _handle_redis_message(self, data: str) -> None:
        """Handle incoming message from Redis and broadcast to WebSocket clients.

        Args:
            data: JSON-encoded message from Redis
        """
        try:
            # Parse the message
            message = json.loads(data)

            # Add to feed
            msg_type = message.get("type", "unknown")
            payload = message.get("payload", {})
            content = payload.get("content", str(payload)[:100]) if isinstance(payload, dict) else str(payload)[:100]

            self.add_feed_item(
                item_id=str(uuid.uuid4()),
                item_type=msg_type,
                content=content,
                source="agent",
            )

            # Broadcast to all WebSocket clients
            await self._connection_manager.broadcast(data)
            logger.debug("Broadcast message to %d clients", self._connection_manager.connection_count)

        except json.JSONDecodeError:
            logger.warning("Received invalid JSON from Redis: %s", data[:100])
        except Exception as e:
            logger.exception("Error handling Redis message: %s", e)

    async def broadcast_message(self, message: str | dict[str, Any]) -> None:
        """Broadcast a message to all connected WebSocket clients.

        Args:
            message: Message to broadcast
        """
        await self._connection_manager.broadcast(message)

    @property
    def websocket_client_count(self) -> int:
        """Get the number of connected WebSocket clients."""
        return self._connection_manager.connection_count


def create_web_app(
    settings: Settings,
    redis_bus: RedisBus | None = None,
    message_router: MessageRouter | None = None,
) -> tuple[WebAdapter, FastAPI]:
    """Create web adapter and return the FastAPI app.

    Args:
        settings: Application settings
        redis_bus: Optional Redis bus for pub/sub
        message_router: Optional message router for centralized subscriptions

    Returns:
        Tuple of (WebAdapter instance, FastAPI app)
    """
    adapter = WebAdapter(settings, redis_bus, message_router)
    return adapter, adapter.app
