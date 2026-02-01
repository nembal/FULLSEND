#!/usr/bin/env python3
"""
Real-time dashboard API for Fullsend agent system.

Subscribes to all fullsend:* Redis channels and exposes:
  GET /api/events     → Recent events across all channels
  GET /api/services   → Service status (last seen timestamps)  
  GET /                → Dashboard HTML

Usage: python dashboard_api.py [--port 8050]
"""

import argparse
import asyncio
import json
import os
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Redis channels to monitor
CHANNELS = [
    "fullsend:discord_raw",
    "fullsend:to_orchestrator",
    "fullsend:from_orchestrator",
    "fullsend:to_fullsend",
    "fullsend:builder_tasks",
    "fullsend:builder_results",
    "fullsend:experiment_results",
    "fullsend:execute_now",
    "fullsend:metrics",
    "fullsend:schedules",
]

# Map channels to source service for status tracking
CHANNEL_TO_SERVICE = {
    "fullsend:discord_raw": "discord",
    "fullsend:to_orchestrator": "watcher",  # watcher escalates here
    "fullsend:from_orchestrator": "orchestrator",
    "fullsend:to_fullsend": "orchestrator",
    "fullsend:builder_tasks": "fullsend",
    "fullsend:builder_results": "builder",
    "fullsend:experiment_results": "executor",
    "fullsend:execute_now": "fullsend",
    "fullsend:metrics": "executor",
    "fullsend:schedules": "orchestrator",
}

# All services we track
ALL_SERVICES = [
    "discord",
    "watcher", 
    "orchestrator",
    "executor",
    "redis_agent",
    "fullsend",
    "builder",
    "roundtable",
]

ROOT = Path(__file__).resolve().parent
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")


@dataclass
class EventBuffer:
    """Thread-safe ring buffer for recent events."""
    
    max_size: int = 100
    events: deque = field(default_factory=lambda: deque(maxlen=100))
    service_last_seen: dict = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    
    def add_event(self, channel: str, data: dict) -> None:
        """Add an event and update service last-seen time."""
        event = {
            "channel": channel,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self.lock:
            self.events.append(event)
            # Update service last seen
            service = CHANNEL_TO_SERVICE.get(channel)
            if service:
                self.service_last_seen[service] = time.time()
            # Also check message type for more specific service detection
            msg_type = data.get("type", "")
            if "redis_agent" in msg_type or data.get("source") == "redis_agent":
                self.service_last_seen["redis_agent"] = time.time()
            if "roundtable" in msg_type or data.get("source") == "roundtable":
                self.service_last_seen["roundtable"] = time.time()
    
    def get_events(self, limit: int = 50) -> list[dict]:
        """Get recent events, newest first."""
        with self.lock:
            events = list(self.events)
        return list(reversed(events))[:limit]
    
    def get_service_status(self) -> dict[str, dict]:
        """Get status for all services."""
        now = time.time()
        with self.lock:
            last_seen = dict(self.service_last_seen)
        
        result = {}
        for service in ALL_SERVICES:
            seen = last_seen.get(service)
            if seen:
                ago = now - seen
                result[service] = {
                    "status": "active" if ago < 30 else "idle",
                    "last_seen": ago,
                    "last_seen_formatted": _format_ago(ago),
                }
            else:
                result[service] = {
                    "status": "unknown",
                    "last_seen": None,
                    "last_seen_formatted": "never",
                }
        return result


def _format_ago(seconds: float) -> str:
    """Format seconds ago as human readable."""
    if seconds < 60:
        return f"{int(seconds)}s ago"
    elif seconds < 3600:
        return f"{int(seconds/60)}m ago"
    else:
        return f"{int(seconds/3600)}h ago"


# Global event buffer
event_buffer = EventBuffer()


def run_redis_subscriber():
    """Background thread that subscribes to Redis channels."""
    try:
        import redis
    except ImportError:
        print("Redis not available, running in demo mode", file=sys.stderr)
        return
    
    def subscribe_loop():
        while True:
            try:
                r = redis.from_url(REDIS_URL, decode_responses=True)
                pubsub = r.pubsub()
                
                # Subscribe to all channels
                for channel in CHANNELS:
                    pubsub.subscribe(channel)
                print(f"Subscribed to {len(CHANNELS)} Redis channels")
                
                # Listen for messages
                for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                        except json.JSONDecodeError:
                            data = {"raw": message["data"]}
                        event_buffer.add_event(message["channel"], data)
                        
            except redis.ConnectionError as e:
                print(f"Redis connection error: {e}, retrying in 5s...")
                time.sleep(5)
            except Exception as e:
                print(f"Redis subscriber error: {e}, retrying in 5s...")
                time.sleep(5)
    
    thread = threading.Thread(target=subscribe_loop, daemon=True)
    thread.start()


def create_app():
    """Create Flask app with API endpoints."""
    try:
        from flask import Flask, jsonify, send_from_directory, request
    except ImportError:
        print("Install Flask: pip install flask", file=sys.stderr)
        sys.exit(1)
    
    app = Flask(__name__)
    
    @app.route("/api/events")
    def api_events():
        """Get recent events across all channels."""
        limit = request.args.get("limit", 50, type=int)
        return jsonify({
            "events": event_buffer.get_events(limit),
            "count": len(event_buffer.events),
        })
    
    @app.route("/api/services")
    def api_services():
        """Get service status."""
        return jsonify({
            "services": event_buffer.get_service_status(),
        })
    
    @app.route("/api/inject", methods=["POST"])
    def api_inject():
        """Inject a test event (for testing without Redis)."""
        data = request.get_json() or {}
        channel = data.get("channel", "fullsend:test")
        payload = data.get("payload", {"type": "test"})
        event_buffer.add_event(channel, payload)
        return jsonify({"ok": True})
    
    @app.route("/")
    def index():
        return send_from_directory(ROOT, "realtime_dashboard.html")
    
    @app.route("/<path:filename>")
    def static_files(filename):
        return send_from_directory(ROOT, filename)
    
    return app


def main():
    parser = argparse.ArgumentParser(description="Real-time dashboard API")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()
    
    # Start Redis subscriber in background
    run_redis_subscriber()
    
    # Start Flask
    app = create_app()
    print(f"\n  Dashboard: http://{args.host}:{args.port}/")
    print(f"  API:       http://{args.host}:{args.port}/api/events")
    print(f"  Services:  http://{args.host}:{args.port}/api/services\n")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
