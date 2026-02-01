"""Unit tests for the classifier module."""

import pytest

from services.watcher.classifier import Classification, parse_classification


class TestParseClassification:
    """Tests for parse_classification function."""

    def test_parse_valid_json_answer(self):
        """Test parsing valid JSON with action=answer."""
        response = '{"action": "answer", "reason": "Simple status query", "priority": "low", "suggested_response": "System is running"}'
        result = parse_classification(response)

        assert result.action == "answer"
        assert result.reason == "Simple status query"
        assert result.priority == "low"
        assert result.suggested_response == "System is running"

    def test_parse_valid_json_escalate(self):
        """Test parsing valid JSON with action=escalate."""
        response = '{"action": "escalate", "reason": "New GTM idea from user", "priority": "high"}'
        result = parse_classification(response)

        assert result.action == "escalate"
        assert result.reason == "New GTM idea from user"
        assert result.priority == "high"
        assert result.suggested_response is None

    def test_parse_valid_json_ignore(self):
        """Test parsing valid JSON with action=ignore."""
        response = '{"action": "ignore", "reason": "Off-topic chatter", "priority": "low"}'
        result = parse_classification(response)

        assert result.action == "ignore"
        assert result.reason == "Off-topic chatter"
        assert result.priority == "low"

    def test_parse_json_in_markdown_code_block(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        response = '''Here is the classification:

```json
{"action": "answer", "reason": "Status query", "priority": "low"}
```
'''
        result = parse_classification(response)

        assert result.action == "answer"
        assert result.reason == "Status query"
        assert result.priority == "low"

    def test_parse_json_in_plain_code_block(self):
        """Test parsing JSON wrapped in plain code blocks."""
        response = '''```
{"action": "escalate", "reason": "Help request", "priority": "medium"}
```'''
        result = parse_classification(response)

        assert result.action == "escalate"
        assert result.reason == "Help request"
        assert result.priority == "medium"

    def test_parse_json_with_surrounding_text(self):
        """Test parsing JSON embedded in surrounding text."""
        response = 'Based on the message, I classify it as: {"action": "ignore", "reason": "Bot message", "priority": "low"} - this is my decision.'
        result = parse_classification(response)

        assert result.action == "ignore"
        assert result.reason == "Bot message"

    def test_parse_invalid_action_defaults_to_escalate(self):
        """Test that invalid action values default to escalate."""
        response = '{"action": "invalid_action", "reason": "Test", "priority": "low"}'
        result = parse_classification(response)

        assert result.action == "escalate"
        assert result.reason == "Test"

    def test_parse_invalid_priority_defaults_to_medium(self):
        """Test that invalid priority values default to medium."""
        response = '{"action": "answer", "reason": "Test", "priority": "invalid_priority"}'
        result = parse_classification(response)

        assert result.action == "answer"
        assert result.priority == "medium"

    def test_parse_missing_reason_provides_default(self):
        """Test that missing reason gets a default value."""
        response = '{"action": "ignore", "priority": "low"}'
        result = parse_classification(response)

        assert result.action == "ignore"
        assert result.reason == "No reason provided"

    def test_parse_missing_priority_defaults_to_medium(self):
        """Test that missing priority defaults to medium."""
        response = '{"action": "answer", "reason": "Test query"}'
        result = parse_classification(response)

        assert result.action == "answer"
        assert result.priority == "medium"

    def test_parse_invalid_json_defaults_to_escalate(self):
        """Test that unparseable JSON defaults to escalate for safety."""
        response = "This is not valid JSON at all"
        result = parse_classification(response)

        assert result.action == "escalate"
        assert "parsing failed" in result.reason.lower()
        assert result.priority == "medium"

    def test_parse_empty_response_defaults_to_escalate(self):
        """Test that empty response defaults to escalate."""
        result = parse_classification("")

        assert result.action == "escalate"
        assert result.priority == "medium"

    def test_parse_json_with_extra_fields_ignored(self):
        """Test that extra fields in JSON are ignored."""
        response = '{"action": "answer", "reason": "Test", "priority": "low", "extra_field": "ignored"}'
        result = parse_classification(response)

        assert result.action == "answer"
        assert result.reason == "Test"
        assert result.priority == "low"


class TestClassificationModel:
    """Tests for Classification Pydantic model."""

    def test_classification_defaults(self):
        """Test Classification model default values."""
        classification = Classification(action="ignore", reason="Test")

        assert classification.priority == "medium"
        assert classification.suggested_response is None

    def test_classification_all_fields(self):
        """Test Classification model with all fields."""
        classification = Classification(
            action="answer",
            reason="Status query",
            priority="low",
            suggested_response="System is running",
        )

        assert classification.action == "answer"
        assert classification.reason == "Status query"
        assert classification.priority == "low"
        assert classification.suggested_response == "System is running"

    def test_classification_action_validation(self):
        """Test that action must be one of the allowed values."""
        with pytest.raises(ValueError):
            Classification(action="invalid", reason="Test")

    def test_classification_priority_validation(self):
        """Test that priority must be one of the allowed values."""
        with pytest.raises(ValueError):
            Classification(action="ignore", reason="Test", priority="invalid")

    def test_classification_serialization(self):
        """Test that Classification can be serialized to JSON."""
        classification = Classification(
            action="escalate",
            reason="New idea",
            priority="high",
        )

        json_str = classification.model_dump_json()
        assert '"action":"escalate"' in json_str.replace(" ", "")
        assert '"priority":"high"' in json_str.replace(" ", "")
