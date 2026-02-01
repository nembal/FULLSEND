#!/usr/bin/env python3
"""
Backend API for the agent dashboard. Reads Demo_logs.txt, aggregates agent_run
events, and serves stats plus the dashboard HTML.

Endpoints:
  GET /api/agent-stats  → JSON { agents: [{ agent, label, count, total_sec, avg_sec }], ... }
  GET /                 → agent_dashboard.html
  GET /agent_dashboard.html → dashboard

Usage: python dashboard_api.py [--port 8050]
Then open http://localhost:8050/agent_dashboard.html
"""

import argparse
import json
import sys
from pathlib import Path

# Project root (directory containing this script and Demo_logs.txt)
ROOT = Path(__file__).resolve().parent
DEMO_LOG_PATH = ROOT / "Demo_logs.txt"

AGENT_LABELS = {
    "roundtable": "Roundtable",
    "orchestrator": "Orchestrator",
    "analyzer": "Analyzer",
    "builder": "Builder",
}
AGENT_ORDER = ["roundtable", "orchestrator", "analyzer", "builder"]


def _parse_events(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _aggregate_agent_runs(events: list[dict]) -> dict[str, dict]:
    by_agent = {}
    for ev in events:
        if ev.get("event") != "agent_run" or not ev.get("agent"):
            continue
        agent = str(ev["agent"]).lower()
        try:
            sec = float(ev.get("duration_sec", 0))
        except (TypeError, ValueError):
            continue
        if agent not in by_agent:
            by_agent[agent] = {"count": 0, "total_sec": 0.0}
        by_agent[agent]["count"] += 1
        by_agent[agent]["total_sec"] += sec
    return by_agent


def get_agent_stats() -> dict:
    """Read Demo_logs.txt and return aggregated agent stats for the API."""
    if not DEMO_LOG_PATH.exists():
        return {"agents": [], "demo_log_path": str(DEMO_LOG_PATH), "error": None}

    try:
        text = DEMO_LOG_PATH.read_text(encoding="utf-8")
    except Exception as e:
        return {
            "agents": [],
            "demo_log_path": str(DEMO_LOG_PATH),
            "error": str(e),
        }

    events = _parse_events(text)
    by_agent = _aggregate_agent_runs(events)

    ordered = [a for a in AGENT_ORDER if a in by_agent]
    rest = sorted(k for k in by_agent if k not in AGENT_ORDER)
    agent_keys = ordered + rest

    agents = []
    for agent in agent_keys:
        s = by_agent[agent]
        count = s["count"]
        total_sec = s["total_sec"]
        avg_sec = total_sec / count if count else 0
        agents.append({
            "agent": agent,
            "label": AGENT_LABELS.get(agent, agent),
            "count": count,
            "total_sec": round(total_sec, 2),
            "avg_sec": round(avg_sec, 2),
        })

    return {
        "agents": agents,
        "demo_log_path": str(DEMO_LOG_PATH),
        "error": None,
    }


def create_app():
    try:
        from flask import Flask, jsonify, send_from_directory
    except ImportError:
        print("Install Flask: pip install flask", file=sys.stderr)
        sys.exit(1)

    app = Flask(__name__)

    @app.route("/api/agent-stats")
    def api_agent_stats():
        return jsonify(get_agent_stats())

    @app.route("/")
    def index():
        return send_from_directory(ROOT, "agent_dashboard.html")

    @app.route("/agent_dashboard.html")
    def dashboard():
        return send_from_directory(ROOT, "agent_dashboard.html")

    return app


def main():
    parser = argparse.ArgumentParser(description="Agent dashboard API server")
    parser.add_argument("--port", type=int, default=8050, help="Port (default 8050)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Bind host (default 127.0.0.1)")
    args = parser.parse_args()

    app = create_app()
    print(f"Dashboard API: http://{args.host}:{args.port}/agent_dashboard.html")
    print("API: GET http://{0}:{1}/api/agent-stats".format(args.host, args.port))
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
