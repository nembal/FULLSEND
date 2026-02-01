"""Unit tests for the agent module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.orchestrator.agent import (
    VALID_ACTIONS,
    VALID_PRIORITIES,
    _extract_content_from_response,
    _extract_json_from_text,
    _format_experiments_summary,
    _format_metrics_summary,
    _validate_action,
    _validate_priority,
    build_prompt,
    load_prompt,
    parse_decision,
)
from services.orchestrator.context import Context
from services.orchestrator.dispatcher import Decision


class TestValidActions:
    """Tests for VALID_ACTIONS constant."""

    def test_contains_expected_actions(self):
        """Test VALID_ACTIONS contains all PRD-defined actions."""
        expected_actions = {
            "dispatch_to_fullsend",
            "dispatch_to_builder",
            "respond_to_discord",
            "update_worklist",
            "record_learning",
            "kill_experiment",
            "initiate_roundtable",
            "no_action",
        }
        assert VALID_ACTIONS == expected_actions


class TestValidPriorities:
    """Tests for VALID_PRIORITIES constant."""

    def test_contains_expected_priorities(self):
        """Test VALID_PRIORITIES contains all PRD-defined priorities."""
        expected_priorities = {"low", "medium", "high", "urgent"}
        assert VALID_PRIORITIES == expected_priorities


class TestValidateAction:
    """Tests for _validate_action function."""

    def test_valid_action_returned_unchanged(self):
        """Test valid actions are returned as-is."""
        for action in VALID_ACTIONS:
            assert _validate_action(action) == action

    def test_invalid_action_defaults_to_no_action(self):
        """Test invalid action defaults to no_action."""
        assert _validate_action("invalid_action") == "no_action"
        assert _validate_action("") == "no_action"
        assert _validate_action("DISPATCH_TO_FULLSEND") == "dispatch_to_fullsend"

    def test_action_is_lowercased(self):
        """Test action is lowercased before validation."""
        assert _validate_action("DISPATCH_TO_FULLSEND") == "dispatch_to_fullsend"
        assert _validate_action("No_Action") == "no_action"

    def test_action_is_stripped(self):
        """Test action is stripped of whitespace."""
        assert _validate_action("  no_action  ") == "no_action"


class TestValidatePriority:
    """Tests for _validate_priority function."""

    def test_valid_priority_returned_unchanged(self):
        """Test valid priorities are returned as-is."""
        for priority in VALID_PRIORITIES:
            assert _validate_priority(priority) == priority

    def test_invalid_priority_defaults_to_medium(self):
        """Test invalid priority defaults to medium."""
        assert _validate_priority("invalid") == "medium"
        assert _validate_priority("") == "medium"

    def test_priority_is_lowercased(self):
        """Test priority is lowercased before validation."""
        assert _validate_priority("HIGH") == "high"
        assert _validate_priority("Medium") == "medium"

    def test_priority_is_stripped(self):
        """Test priority is stripped of whitespace."""
        assert _validate_priority("  high  ") == "high"


class TestExtractJsonFromText:
    """Tests for _extract_json_from_text function."""

    def test_extract_fenced_json_block(self):
        """Test extracting JSON from fenced code block."""
        text = '''Here is my decision:

```json
{"action": "no_action", "reasoning": "Test"}
```

That's it.'''
        result = _extract_json_from_text(text)
        assert '"action": "no_action"' in result

    def test_extract_raw_json(self):
        """Test extracting raw JSON from text."""
        text = 'My decision is {"action": "dispatch_to_fullsend", "reasoning": "Test"} - done.'
        result = _extract_json_from_text(text)
        assert '"action": "dispatch_to_fullsend"' in result

    def test_extract_nested_json(self):
        """Test extracting nested JSON with balanced braces."""
        text = '''{"action": "dispatch_to_fullsend", "payload": {"idea": {"name": "Test"}}}'''
        result = _extract_json_from_text(text)
        assert result == text

    def test_raises_on_no_json(self):
        """Test raises ValueError when no JSON found."""
        with pytest.raises(ValueError, match="No JSON found"):
            _extract_json_from_text("This is plain text with no JSON")

    def test_handles_incomplete_fenced_block(self):
        """Test handles incomplete fenced code block by falling back to brace matching."""
        text = '''```json
{"action": "no_action"}'''
        # Should fall back to brace matching since closing ``` is missing
        result = _extract_json_from_text(text)
        assert '"action": "no_action"' in result


class TestFormatExperimentsSummary:
    """Tests for _format_experiments_summary function."""

    def test_empty_experiments_returns_placeholder(self):
        """Test empty list returns placeholder text."""
        result = _format_experiments_summary([])
        assert result == "(No active experiments)"

    def test_formats_experiments_as_list(self):
        """Test experiments are formatted as bullet list."""
        experiments = [
            {"id": "exp_1", "name": "Test Campaign", "state": "running"},
            {"id": "exp_2", "summary": "Cold Email", "state": "paused"},
        ]
        result = _format_experiments_summary(experiments)

        assert "- exp_1: Test Campaign (state: running)" in result
        assert "- exp_2: Cold Email (state: paused)" in result

    def test_handles_missing_fields(self):
        """Test handles experiments with missing fields."""
        experiments = [{"state": "active"}]
        result = _format_experiments_summary(experiments)

        assert "unknown: unnamed" in result


class TestFormatMetricsSummary:
    """Tests for _format_metrics_summary function."""

    def test_empty_metrics_returns_placeholder(self):
        """Test empty dict returns placeholder text."""
        result = _format_metrics_summary({})
        assert result == "(No recent metrics)"

    def test_formats_dict_metrics(self):
        """Test dict metrics are formatted as key=value pairs."""
        metrics = {
            "exp_1": {"response_rate": 0.15, "open_rate": 0.45},
        }
        result = _format_metrics_summary(metrics)

        assert "- exp_1:" in result
        assert "response_rate=0.15" in result
        assert "open_rate=0.45" in result

    def test_formats_simple_metrics(self):
        """Test simple value metrics are formatted directly."""
        metrics = {"exp_1": 0.15}
        result = _format_metrics_summary(metrics)

        assert "- exp_1: 0.15" in result


class TestBuildPrompt:
    """Tests for build_prompt function."""

    @pytest.fixture
    def sample_context(self):
        """Create sample context for testing."""
        return Context(
            product="Test Product Description",
            worklist="## Worklist\n- Task 1",
            learnings="## Learnings\n- Insight 1",
            active_experiments=[{"id": "exp_1", "name": "Test", "state": "running"}],
            available_tools=["scraper", "sender"],
            recent_metrics={"exp_1": {"rate": 0.15}},
        )

    def test_includes_message_info(self, sample_context):
        """Test prompt includes message information."""
        msg = {"type": "escalation", "source": "watcher", "priority": "high"}
        result = build_prompt(msg, sample_context)

        assert "Type: escalation" in result
        assert "Source: watcher" in result
        assert "Priority: high" in result

    def test_includes_all_context_sections(self, sample_context):
        """Test prompt includes all context sections."""
        msg = {"type": "test"}
        result = build_prompt(msg, sample_context)

        assert "Test Product Description" in result
        assert "Worklist" in result
        assert "Learnings" in result
        assert "exp_1: Test" in result
        assert "scraper, sender" in result
        assert "rate=0.15" in result

    def test_includes_valid_actions(self, sample_context):
        """Test prompt includes list of valid actions."""
        msg = {"type": "test"}
        result = build_prompt(msg, sample_context)

        assert "Valid actions:" in result
        for action in VALID_ACTIONS:
            assert action in result


class TestExtractContentFromResponse:
    """Tests for _extract_content_from_response function."""

    def test_extracts_text_content(self):
        """Test extracts text content from response."""
        mock_response = MagicMock()
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = '{"action": "no_action"}'
        mock_response.content = [mock_text_block]

        text, thinking = _extract_content_from_response(mock_response)

        assert text == '{"action": "no_action"}'
        assert thinking is None

    def test_extracts_thinking_content(self):
        """Test extracts thinking content from response."""
        mock_response = MagicMock()
        mock_thinking_block = MagicMock()
        mock_thinking_block.type = "thinking"
        mock_thinking_block.thinking = "Let me think about this..."
        mock_text_block = MagicMock()
        mock_text_block.type = "text"
        mock_text_block.text = '{"action": "no_action"}'
        mock_response.content = [mock_thinking_block, mock_text_block]

        text, thinking = _extract_content_from_response(mock_response)

        assert text == '{"action": "no_action"}'
        assert thinking == "Let me think about this..."


class TestParseDecision:
    """Tests for parse_decision function."""

    def _make_mock_response(self, text_content, thinking_content=None):
        """Helper to create mock API response."""
        mock_response = MagicMock()
        blocks = []
        if thinking_content:
            mock_thinking = MagicMock()
            mock_thinking.type = "thinking"
            mock_thinking.thinking = thinking_content
            blocks.append(mock_thinking)
        mock_text = MagicMock()
        mock_text.type = "text"
        mock_text.text = text_content
        blocks.append(mock_text)
        mock_response.content = blocks
        return mock_response

    def test_parses_valid_json_decision(self):
        """Test parsing valid JSON decision."""
        response = self._make_mock_response(
            '{"action": "dispatch_to_fullsend", "reasoning": "Good idea", "payload": {"idea": "Test"}, "priority": "high"}'
        )
        decision = parse_decision(response)

        assert decision.action == "dispatch_to_fullsend"
        assert decision.reasoning == "Good idea"
        assert decision.payload == {"idea": "Test"}
        assert decision.priority == "high"

    def test_parses_json_in_code_block(self):
        """Test parsing JSON wrapped in code block."""
        response = self._make_mock_response(
            '''Here is my decision:

```json
{"action": "respond_to_discord", "reasoning": "Status query", "payload": {"content": "Hello"}, "priority": "low"}
```'''
        )
        decision = parse_decision(response)

        assert decision.action == "respond_to_discord"
        assert decision.priority == "low"

    def test_validates_action(self):
        """Test invalid action is defaulted to no_action."""
        response = self._make_mock_response(
            '{"action": "invalid_action", "reasoning": "Test", "payload": {}, "priority": "medium"}'
        )
        decision = parse_decision(response)

        assert decision.action == "no_action"

    def test_validates_priority(self):
        """Test invalid priority is defaulted to medium."""
        response = self._make_mock_response(
            '{"action": "no_action", "reasoning": "Test", "payload": {}, "priority": "invalid"}'
        )
        decision = parse_decision(response)

        assert decision.priority == "medium"

    def test_wraps_non_dict_payload(self):
        """Test non-dict payload is wrapped in dict."""
        response = self._make_mock_response(
            '{"action": "no_action", "reasoning": "Test", "payload": "string_payload", "priority": "low"}'
        )
        decision = parse_decision(response)

        assert decision.payload == {"value": "string_payload"}

    def test_extracts_experiment_id_for_kill(self):
        """Test extracts experiment_id for kill_experiment action."""
        response = self._make_mock_response(
            '{"action": "kill_experiment", "reasoning": "Failing", "experiment_id": "exp_123", "payload": {}, "priority": "high"}'
        )
        decision = parse_decision(response)

        assert decision.action == "kill_experiment"
        assert decision.experiment_id == "exp_123"

    def test_extracts_context_for_fullsend(self):
        """Test extracts context_for_fullsend for dispatch action."""
        response = self._make_mock_response(
            '{"action": "dispatch_to_fullsend", "reasoning": "Good idea", "context_for_fullsend": "Use email scraper", "payload": {}, "priority": "medium"}'
        )
        decision = parse_decision(response)

        assert decision.action == "dispatch_to_fullsend"
        assert decision.context_for_fullsend == "Use email scraper"

    def test_returns_fallback_on_invalid_json(self):
        """Test returns fallback decision on invalid JSON."""
        response = self._make_mock_response("This is not valid JSON at all")
        decision = parse_decision(response)

        assert decision.action == "no_action"
        assert "JSON" in decision.reasoning or "No JSON" in decision.reasoning

    def test_returns_fallback_on_empty_response(self):
        """Test returns fallback decision on empty text content."""
        mock_response = MagicMock()
        mock_response.content = []
        decision = parse_decision(mock_response)

        assert decision.action == "no_action"
        assert "No text content" in decision.reasoning

    def test_handles_missing_optional_fields(self):
        """Test handles missing optional fields with defaults."""
        response = self._make_mock_response(
            '{"action": "no_action"}'
        )
        decision = parse_decision(response)

        assert decision.action == "no_action"
        assert decision.reasoning == ""
        assert decision.payload == {}
        assert decision.priority == "medium"


class TestDecisionDataclass:
    """Tests for Decision dataclass."""

    def test_decision_creation(self):
        """Test Decision can be created with required fields."""
        decision = Decision(
            action="dispatch_to_fullsend",
            reasoning="Good idea",
            payload={"idea": "Test"},
            priority="high",
        )

        assert decision.action == "dispatch_to_fullsend"
        assert decision.reasoning == "Good idea"
        assert decision.priority == "high"

    def test_decision_optional_fields_default_to_none(self):
        """Test optional fields default to None."""
        decision = Decision(
            action="no_action",
            reasoning="Test",
            payload={},
            priority="low",
        )

        assert decision.experiment_id is None
        assert decision.context_for_fullsend is None

    def test_decision_with_all_fields(self):
        """Test Decision with all fields populated."""
        decision = Decision(
            action="kill_experiment",
            reasoning="Failing badly",
            payload={"reason": "Low response rate"},
            priority="high",
            experiment_id="exp_123",
            context_for_fullsend="Context here",
        )

        assert decision.experiment_id == "exp_123"
        assert decision.context_for_fullsend == "Context here"
