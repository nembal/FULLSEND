"""
Thin wrapper around Stagehand Python SDK with Browserbase.
Exposes: session create/close, navigate, act, extract, observe.
Forms: use act() with natural language (e.g. "fill the email field with X", "click Submit").
"""

import logging
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class StagehandSession:
    """Wrapper for a Stagehand browser session (Browserbase)."""

    def __init__(self, client: Any, session: Any):
        self._client = client
        self._session = session

    @property
    def id(self) -> str:
        return getattr(self._session, "id", "") or ""

    async def navigate(self, url: str) -> dict[str, Any]:
        """Navigate to URL. Returns result message or error."""
        try:
            r = await self._session.navigate(url=url)
            msg = getattr(getattr(r, "data", None), "result", None)
            if hasattr(msg, "message"):
                return {"ok": True, "message": msg.message}
            return {"ok": True, "message": str(msg) if msg else "navigated"}
        except Exception as e:
            logger.exception("navigate failed: %s", e)
            return {"ok": False, "error": str(e)}

    async def act(self, input_spec: str | dict[str, Any]) -> dict[str, Any]:
        """Perform action (natural language or action dict from observe). Forms: e.g. 'fill the email field with X', 'click Submit'."""
        try:
            r = await self._session.act(input=input_spec)
            msg = getattr(getattr(r, "data", None), "result", None)
            if hasattr(msg, "message"):
                return {"ok": True, "message": msg.message}
            return {"ok": True, "message": str(msg) if msg else "done"}
        except Exception as e:
            logger.exception("act failed: %s", e)
            return {"ok": False, "error": str(e)}

    async def extract(self, instruction: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        """Extract data from page. Optional schema for structured output."""
        try:
            kwargs = {"instruction": instruction}
            if schema:
                kwargs["schema"] = schema
            r = await self._session.extract(**kwargs)
            result = getattr(getattr(r, "data", None), "result", None)
            return {"ok": True, "data": result}
        except Exception as e:
            logger.exception("extract failed: %s", e)
            return {"ok": False, "error": str(e)}

    async def observe(self, instruction: str) -> dict[str, Any]:
        """Observe and find actionable elements. Returns list of actions (can be passed to act)."""
        try:
            r = await self._session.observe(instruction=instruction)
            result = getattr(getattr(r, "data", None), "result", None)
            items = result if isinstance(result, list) else []
            actions = []
            for item in items:
                if hasattr(item, "to_dict"):
                    actions.append(item.to_dict(exclude_none=True))
                elif isinstance(item, dict):
                    actions.append(item)
                else:
                    actions.append({"description": str(item)})
            return {"ok": True, "actions": actions}
        except Exception as e:
            logger.exception("observe failed: %s", e)
            return {"ok": False, "error": str(e), "actions": []}

    async def end(self) -> None:
        """Close the browser session."""
        try:
            await self._session.end()
        except Exception as e:
            logger.warning("session.end failed: %s", e)


async def create_stagehand_session(model_name: str = "anthropic/claude-sonnet-4-20250514") -> StagehandSession | None:
    """
    Create a Stagehand session with Browserbase.
    Requires BROWSERBASE_API_KEY, BROWSERBASE_PROJECT_ID, MODEL_API_KEY (or ANTHROPIC_API_KEY).
    Returns None if config missing or create fails.
    """
    from .config import get_browserbase_api_key, get_browserbase_project_id, get_model_api_key

    api_key = get_browserbase_api_key()
    project_id = get_browserbase_project_id()
    model_api_key = get_model_api_key()
    if not api_key or not project_id or not model_api_key:
        logger.warning("Missing BROWSERBASE_API_KEY, BROWSERBASE_PROJECT_ID, or MODEL_API_KEY")
        return None
    try:
        from stagehand import AsyncStagehand

        client = AsyncStagehand(
            browserbase_api_key=api_key,
            browserbase_project_id=project_id,
            model_api_key=model_api_key,
        )
        session = await client.sessions.create(model_name=model_name)
        return StagehandSession(client, session)
    except Exception as e:
        logger.exception("create_stagehand_session failed: %s", e)
        return None
