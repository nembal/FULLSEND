"""Main entry point for the Discord Communication Service."""

import asyncio
import logging
import signal
import sys
from contextlib import suppress

import uvicorn

from .adapters.discord_adapter import DiscordAdapter
from .adapters.web_adapter import WebAdapter, create_web_app
from .config import get_settings
from .core.bus import RedisBus
from .core.router import MessageRouter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class ServiceRunner:
    """Orchestrates running Discord and Web adapters based on config."""

    def __init__(self) -> None:
        """Initialize the service runner."""
        self.settings = get_settings()
        self.redis_bus: RedisBus | None = None
        self.message_router: MessageRouter | None = None
        self.discord_adapter: DiscordAdapter | None = None
        self.web_adapter: WebAdapter | None = None
        self._shutdown_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    async def _connect_redis(self) -> None:
        """Connect to Redis bus and initialize message router."""
        self.redis_bus = RedisBus(self.settings.redis_url)
        try:
            await self.redis_bus.connect()
            logger.info("Connected to Redis")

            # Initialize and start message router
            self.message_router = MessageRouter(self.redis_bus)
            await self.message_router.start()
            logger.info("Message router started")
        except ConnectionError as e:
            logger.warning(f"Redis connection failed: {e}. Running in offline mode.")
            self.redis_bus = None
            self.message_router = None

    async def _disconnect_redis(self) -> None:
        """Stop message router and disconnect from Redis bus."""
        if self.message_router:
            await self.message_router.stop()
            logger.info("Message router stopped")

        if self.redis_bus:
            await self.redis_bus.disconnect()
            logger.info("Disconnected from Redis")

    async def _start_discord(self) -> None:
        """Start the Discord adapter."""
        logger.info("Starting Discord adapter...")
        self.discord_adapter = DiscordAdapter(
            self.settings,
            self.redis_bus,
            self.message_router,
        )
        try:
            await self.discord_adapter.start()
        except asyncio.CancelledError:
            logger.info("Discord adapter task cancelled")
        except Exception as e:
            logger.error(f"Discord adapter error: {e}")
            raise

    async def _start_web(self) -> None:
        """Start the FastAPI web adapter."""
        logger.info(f"Starting web adapter on port {self.settings.web_port}...")
        self.web_adapter, app = create_web_app(
            self.settings,
            self.redis_bus,
            self.message_router,
        )

        # Initialize web adapter (subscribes to Redis early)
        await self.web_adapter.init()

        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=self.settings.web_port,
            log_level="info",
        )
        server = uvicorn.Server(config)

        try:
            await server.serve()
        except asyncio.CancelledError:
            logger.info("Web adapter task cancelled")

    async def _shutdown(self) -> None:
        """Perform graceful shutdown."""
        logger.info("Initiating graceful shutdown...")

        # Signal shutdown
        self._shutdown_event.set()

        # Cancel all running tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        # Stop Discord adapter
        if self.discord_adapter:
            await self.discord_adapter.stop()
            logger.info("Discord adapter stopped")

        # Disconnect Redis
        await self._disconnect_redis()

        logger.info("Shutdown complete")

    def _setup_signal_handlers(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set up signal handlers for graceful shutdown."""
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(self._shutdown()),
            )

    async def run(self) -> None:
        """Run the service based on ENV configuration."""
        logger.info(f"Starting Fullsend Communication Service in '{self.settings.env}' mode")

        # Set up signal handlers
        loop = asyncio.get_running_loop()
        self._setup_signal_handlers(loop)

        # Connect to Redis
        await self._connect_redis()

        try:
            # Start adapters based on ENV mode
            if self.settings.should_run_discord and self.settings.should_run_web:
                # Run both adapters concurrently
                logger.info("Starting both Discord and Web adapters...")
                discord_task = asyncio.create_task(self._start_discord())
                web_task = asyncio.create_task(self._start_web())
                self._tasks = [discord_task, web_task]
                await asyncio.gather(*self._tasks, return_exceptions=True)

            elif self.settings.should_run_discord:
                # Run Discord only
                logger.info("Starting Discord adapter only...")
                discord_task = asyncio.create_task(self._start_discord())
                self._tasks = [discord_task]
                await discord_task

            elif self.settings.should_run_web:
                # Run Web only
                logger.info("Starting Web adapter only...")
                web_task = asyncio.create_task(self._start_web())
                self._tasks = [web_task]
                await web_task

            else:
                logger.error("No adapters configured to run. Check ENV setting.")
                return

        except asyncio.CancelledError:
            logger.info("Service cancelled")
        except Exception as e:
            logger.exception(f"Service error: {e}")
        finally:
            # Ensure clean shutdown
            with suppress(Exception):
                await self._shutdown()


def main() -> None:
    """Main entry point."""
    try:
        runner = ServiceRunner()
        asyncio.run(runner.run())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
