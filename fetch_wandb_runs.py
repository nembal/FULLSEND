#!/usr/bin/env python3
"""
Fetch recent W&B runs or Weave traces for a project and write wandb_runs.json (for demo_viz.html).

Modes:
  default   - List classic W&B runs via wandb.Api().runs() (requires WANDB_PROJECT, API key).
  --traces  - List Weave traces via weave.get_calls() (uses same project; shows the 673 traces).
  --offline - Build from Demo_logs.txt (wandb_run events only), no API call.

Uses WANDB_ENTITY, WANDB_PROJECT from env. For traces, project is entity/project (e.g. viswanathkothe-syracuse-university/weavehacks).

Usage: python fetch_wandb_runs.py [--limit N]
       python fetch_wandb_runs.py --traces [--limit N]
       python fetch_wandb_runs.py --offline
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Output next to this script (project root when run from GTM_agent_auto_mode_on)
OUTPUT_PATH = Path(__file__).resolve().parent / "wandb_runs.json"
DEMO_LOG_PATH = Path(__file__).resolve().parent / "Demo_logs.txt"


def _serialize_run(run) -> dict:
    """Extract a JSON-serializable summary from a wandb Run."""
    entity = getattr(run, "entity", "") or ""
    project = getattr(run, "project", "") or ""
    run_id = getattr(run, "id", "") or ""
    url = f"https://wandb.ai/{entity}/{project}/runs/{run_id}" if (entity and project and run_id) else ""
    created = getattr(run, "created_at", None)
    out = {
        "id": run_id,
        "name": getattr(run, "name", None) or run_id,
        "url": getattr(run, "url", None) or url,
        "created_at": created.isoformat() if created else None,
        "state": getattr(run, "state", None),
    }
    # Summary metrics (e.g. from demo runs)
    summary = getattr(run, "summary", None)
    if summary and hasattr(summary, "_json_dict"):
        try:
            d = summary._json_dict
            for k in ("blocked_before_count", "blocked_after_count", "tasks_published", "tools_added", "requeued"):
                if k in d and d[k] is not None:
                    out[k] = d[k]
        except Exception:
            pass
    config = getattr(run, "config", None)
    if config and hasattr(config, "items"):
        try:
            out["topic"] = config.get("topic", "") or ""
        except Exception:
            pass
    return out


def _build_offline_runs() -> dict:
    """Build wandb_runs.json from Demo_logs.txt (wandb_run events only)."""
    runs = []
    if not DEMO_LOG_PATH.exists():
        return {"runs": runs, "project": None, "entity": None}
    for line in DEMO_LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
            if ev.get("event") == "wandb_run":
                run_id = ev.get("run_id") or ""
                run_url = ev.get("run_url") or ""
                runs.append({
                    "id": run_id,
                    "name": run_id or "demo-run",
                    "url": run_url,
                    "created_at": ev.get("ts"),
                    "state": "finished",
                })
        except json.JSONDecodeError:
            continue
    return {"runs": runs, "project": os.getenv("WANDB_PROJECT"), "entity": os.getenv("WANDB_ENTITY")}


def _fetch_weave_traces(entity: str, project: str, limit: int) -> list[dict]:
    """Fetch Weave traces via weave.init + get_client().get_calls(). Returns list of run-like dicts."""
    import weave
    from weave.trace_server.trace_server_interface import CallsFilter
    from weave.trace_server.common_interface import SortBy

    project_name = f"{entity}/{project}" if entity else project
    weave.init(project_name)
    client = weave.get_client()
    if not client:
        return []

    # Request only trace roots (top-level traces); without this you may get 0 or only child spans
    calls_filter = CallsFilter(trace_roots_only=True)
    sort_by = [SortBy(field="started_at", direction="desc")]
    calls = client.get_calls(
        limit=limit,
        filter=calls_filter,
        sort_by=sort_by,
    )
    list_of_runs = []
    for call in calls:
        started = getattr(call, "started_at", None)
        url = getattr(call, "ui_url", None) or ""
        name = getattr(call, "display_name", None) or getattr(call, "op_name", None) or getattr(call, "id", "")
        list_of_runs.append({
            "id": getattr(call, "id", "") or "",
            "name": name or "",
            "url": url,
            "created_at": started.isoformat() if started else None,
            "state": "finished",
        })
    return list_of_runs


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch recent W&B runs and write wandb_runs.json")
    parser.add_argument("--limit", type=int, default=20, help="Max number of runs to fetch (default 20)")
    parser.add_argument("--entity", type=str, default=None, help="W&B entity (default: WANDB_ENTITY or API default)")
    parser.add_argument("--project", type=str, default=None, help="W&B project (default: WANDB_PROJECT)")
    parser.add_argument("--offline", action="store_true", help="Build from Demo_logs.txt only (no API call)")
    parser.add_argument("--traces", action="store_true", help="Fetch Weave traces (get_calls) instead of classic runs")
    args = parser.parse_args()

    entity = args.entity or os.getenv("WANDB_ENTITY", "")
    project = args.project or os.getenv("WANDB_PROJECT")
    if not project:
        print("Set WANDB_PROJECT in .env or pass --project (or use --offline)", file=sys.stderr)
        return 1

    if args.offline:
        payload = _build_offline_runs()
        OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {len(payload['runs'])} run(s) to {OUTPUT_PATH} (from Demo_logs.txt)")
        return 0

    if args.traces:
        try:
            list_of_runs = _fetch_weave_traces(entity, project, args.limit)
            payload = {"runs": list_of_runs, "project": project, "entity": entity or None}
            OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"Wrote {len(list_of_runs)} trace(s) to {OUTPUT_PATH}")
            return 0
        except Exception as e:
            print(f"Failed to fetch traces: {e}", file=sys.stderr)
            return 1

    api_key = os.getenv("WANDB_API_KEY") or os.getenv("WANDB_KEY")
    if not api_key:
        print("Set WANDB_API_KEY or WANDB_KEY in .env (or use --traces / --offline)", file=sys.stderr)
        return 1

    try:
        import wandb
        api = wandb.Api()
        path = f"{entity}/{project}".strip("/") or project
        runs = api.runs(path, per_page=args.limit)
        list_of_runs = []
        for run in runs:
            list_of_runs.append(_serialize_run(run))
        payload = {"runs": list_of_runs, "project": project, "entity": entity or None}
        OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {len(list_of_runs)} run(s) to {OUTPUT_PATH}")
        return 0
    except Exception as e:
        print(f"Failed to fetch runs: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
