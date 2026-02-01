"""Test plan checks from PRD_ROUNDTABLE.md

These tests validate the roundtable implementation against PRD acceptance criteria.

Run with:
    pytest services/roundtable/test_roundtable.py -v

For integration tests that call the LLM (slow, requires API keys):
    pytest services/roundtable/test_roundtable.py -v -m integration
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Create a proper weave mock that doesn't break decorators
_weave_mock = MagicMock()
_weave_mock.init = MagicMock()
_weave_mock.op = lambda f: f  # Return the function unchanged
sys.modules["weave"] = _weave_mock

# Import roundtable modules (personas module doesn't use weave)
from services.roundtable.personas import ROLES, get_persona, get_summarizer_prompt, load_persona
from services.roundtable.runner import run_roundtable


# ============================================================================
# Unit Tests (no LLM calls, always run)
# ============================================================================

class TestPersonaFiles:
    """PRD: Verify personas/ directory with .txt files exists."""

    def test_personas_directory_exists(self):
        """Verify personas/ directory exists."""
        personas_dir = Path(__file__).parent / "personas"
        assert personas_dir.exists(), "personas/ directory must exist"
        assert personas_dir.is_dir(), "personas/ must be a directory"

    def test_all_persona_files_exist(self):
        """PRD: Verify all 4 persona files exist."""
        expected_files = ["artist.txt", "business.txt", "tech.txt", "summarizer.txt"]
        personas_dir = Path(__file__).parent / "personas"
        for filename in expected_files:
            filepath = personas_dir / filename
            assert filepath.exists(), f"Missing persona file: {filename}"

    def test_persona_files_not_empty(self):
        """Verify persona files have content."""
        for name in ["artist", "business", "tech", "summarizer"]:
            content = load_persona(name)
            assert len(content) > 50, f"Persona '{name}' seems too short"


class TestPersonaContent:
    """PRD: Verify each agent has distinct persona."""

    def test_artist_persona_is_creative(self):
        """ARTIST: Should have creative/unconventional ideas."""
        content = get_persona("artist").lower()
        creative_keywords = ["creative", "outside the box", "unconventional", "metaphor", "what if"]
        matches = [kw for kw in creative_keywords if kw in content]
        assert len(matches) >= 2, f"ARTIST persona should have creative keywords. Found: {matches}"

    def test_business_persona_is_revenue_focused(self):
        """BUSINESS: Should mention metrics, conversion, ROI."""
        content = get_persona("business").lower()
        business_keywords = ["revenue", "roi", "conversion", "metrics", "numbers", "cost"]
        matches = [kw for kw in business_keywords if kw in content]
        assert len(matches) >= 2, f"BUSINESS persona should have business keywords. Found: {matches}"

    def test_tech_persona_is_builder_focused(self):
        """TECH: Should mention specific tools, APIs, automation."""
        content = get_persona("tech").lower()
        tech_keywords = ["tools", "api", "automation", "build", "data", "scraping"]
        matches = [kw for kw in tech_keywords if kw in content]
        assert len(matches) >= 2, f"TECH persona should have tech keywords. Found: {matches}"

    def test_summarizer_has_owner_rules(self):
        """PRD: Summarizer must include WHO should do it (FULLSEND, Builder, Orchestrator)."""
        content = get_summarizer_prompt()
        assert "FULLSEND" in content, "Summarizer prompt must mention FULLSEND owner"
        assert "Builder" in content, "Summarizer prompt must mention Builder owner"
        assert "Orchestrator" in content, "Summarizer prompt must mention Orchestrator owner"
        assert "Owner" in content, "Summarizer prompt must mention task ownership"

    def test_personas_are_distinct(self):
        """PRD: Each agent has distinct persona (not all sound the same)."""
        artist = get_persona("artist").lower()
        business = get_persona("business").lower()
        tech = get_persona("tech").lower()

        # Simple check: personas should be different
        assert artist != business, "ARTIST and BUSINESS personas should be distinct"
        assert artist != tech, "ARTIST and TECH personas should be distinct"
        assert business != tech, "BUSINESS and TECH personas should be distinct"


class TestRoles:
    """Verify ROLES configuration."""

    def test_three_debate_roles(self):
        """PRD: Runs 3-agent debate (ARTIST, BUSINESS, TECH)."""
        assert len(ROLES) == 3, "Should have exactly 3 debate roles"
        assert "artist" in ROLES
        assert "business" in ROLES
        assert "tech" in ROLES

    def test_get_persona_for_all_roles(self):
        """All roles should have loadable personas."""
        for role in ROLES:
            persona = get_persona(role)
            assert isinstance(persona, str)
            assert len(persona) > 0


class TestRunnerDefaults:
    """Verify runner configuration matches PRD."""

    def test_default_max_rounds_is_three(self):
        """PRD: Debate runs for 3 rounds."""
        import inspect
        sig = inspect.signature(run_roundtable)
        max_rounds_param = sig.parameters.get("max_rounds")
        assert max_rounds_param is not None, "max_rounds parameter must exist"
        assert max_rounds_param.default == 3, "Default max_rounds should be 3"

    def test_runner_has_required_parameters(self):
        """Verify runner accepts PRD input parameters."""
        import inspect
        sig = inspect.signature(run_roundtable)
        params = sig.parameters
        assert "prompt" in params, "Should accept 'prompt' parameter"
        assert "context" in params, "Should accept 'context' parameter"
        assert "learnings" in params, "Should accept 'learnings' parameter"
        assert "max_rounds" in params, "Should accept 'max_rounds' parameter"


class TestOutputFormat:
    """Test output format matches PRD spec."""

    def test_output_has_transcript_and_summary(self):
        """PRD: Returns structured output (transcript + summary)."""
        # Mock the LLM to test output structure
        mock_response = MagicMock()
        mock_response.content = "Test response"

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response

        with patch("services.roundtable.runner.get_llm", return_value=mock_llm):
            result = run_roundtable(prompt="Test prompt", max_rounds=1)

        assert "transcript" in result, "Output must have 'transcript' key"
        assert "summary" in result, "Output must have 'summary' key"

    def test_transcript_has_round_headers(self):
        """PRD: Transcript should have round headers."""
        mock_response = MagicMock()
        mock_response.content = "Test response"

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response

        with patch("services.roundtable.runner.get_llm", return_value=mock_llm):
            result = run_roundtable(prompt="Test prompt", max_rounds=2)

        transcript = result["transcript"]
        assert "--- Round 1 ---" in transcript, "Transcript should have Round 1 header"
        assert "--- Round 2 ---" in transcript, "Transcript should have Round 2 header"

    def test_transcript_shows_all_three_agents(self):
        """PRD: Transcript shows 3 agents debating."""
        mock_response = MagicMock()
        mock_response.content = "Agent response"

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response

        with patch("services.roundtable.runner.get_llm", return_value=mock_llm):
            result = run_roundtable(prompt="Test prompt", max_rounds=1)

        transcript = result["transcript"]
        assert "ARTIST:" in transcript, "Transcript should include ARTIST"
        assert "BUSINESS:" in transcript, "Transcript should include BUSINESS"
        assert "TECH:" in transcript, "Transcript should include TECH"

    def test_summary_is_list(self):
        """PRD: Summary should be list of strings (not single string)."""
        mock_response = MagicMock()
        mock_response.content = "- Task 1\n- Task 2\n- Task 3"

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response

        with patch("services.roundtable.runner.get_llm", return_value=mock_llm):
            result = run_roundtable(prompt="Test prompt", max_rounds=1)

        assert isinstance(result["summary"], list), "Summary should be a list"

    def test_summary_max_five_tasks(self):
        """PRD: Summary should have max 5 tasks."""
        mock_response = MagicMock()
        mock_response.content = "- Task 1\n- Task 2\n- Task 3\n- Task 4\n- Task 5\n- Task 6\n- Task 7"

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response

        with patch("services.roundtable.runner.get_llm", return_value=mock_llm):
            result = run_roundtable(prompt="Test prompt", max_rounds=1)

        assert len(result["summary"]) <= 5, "Summary should have max 5 tasks"


class TestInputFormat:
    """Test input format matches PRD spec."""

    def test_accepts_context_parameter(self):
        """PRD: Can include context."""
        mock_response = MagicMock()
        mock_response.content = "Test response"

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response

        with patch("services.roundtable.runner.get_llm", return_value=mock_llm):
            # Should not raise
            result = run_roundtable(
                prompt="Test prompt",
                context="Some context here",
                max_rounds=1
            )

        assert result is not None

    def test_accepts_learnings_parameter(self):
        """PRD: Can include learnings."""
        mock_response = MagicMock()
        mock_response.content = "Test response"

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response

        with patch("services.roundtable.runner.get_llm", return_value=mock_llm):
            # Should not raise
            result = run_roundtable(
                prompt="Test prompt",
                learnings=["Learning 1", "Learning 2"],
                max_rounds=1
            )

        assert result is not None


# ============================================================================
# Integration Tests (call real LLM, requires API keys)
# ============================================================================

@pytest.mark.integration
class TestIntegration:
    """Integration tests that call the real LLM.

    These tests require valid API keys and may incur costs.
    Run with: pytest services/roundtable/test_roundtable.py -v -m integration
    """

    @pytest.fixture
    def skip_if_no_api_key(self):
        """Skip integration tests if no API key is configured."""
        if not (os.getenv("WANDB_KEY") or os.getenv("OPENAI_API_KEY")):
            pytest.skip("No API key configured (WANDB_KEY or OPENAI_API_KEY)")

    def test_basic_roundtable_run(self, skip_if_no_api_key):
        """PRD Basic Test: Run roundtable and verify summary output."""
        result = run_roundtable(
            prompt="How can we reach developers who use competitor products?",
            max_rounds=1  # Minimal for speed
        )

        # Verify structure
        assert "transcript" in result
        assert "summary" in result

        # PRD: Should output 3-5 actionable tasks
        summary = result["summary"]
        assert isinstance(summary, list), "Summary should be a list"
        # Note: LLM might return fewer than 3 in a single round, but structure should be correct

    def test_full_roundtable_run(self, skip_if_no_api_key):
        """PRD Full Test: Run with context and learnings."""
        result = run_roundtable(
            prompt="How can we reach AI startup CTOs who just raised Series A?",
            context="We sell developer tools. Our best customers are technical founders.",
            learnings=[
                "GitHub-based targeting has 15% response rate",
                "Personalization on recent news increases opens 2x"
            ],
            max_rounds=2
        )

        # Verify:
        # - Transcript shows 3 agents debating
        transcript = result["transcript"]
        assert "ARTIST:" in transcript
        assert "BUSINESS:" in transcript
        assert "TECH:" in transcript

        # - Has round headers
        assert "--- Round 1 ---" in transcript
        assert "--- Round 2 ---" in transcript

        # - Summary has tasks (list format)
        assert isinstance(result["summary"], list)


@pytest.mark.integration
class TestCLI:
    """Test CLI interface."""

    @pytest.fixture
    def skip_if_no_api_key(self):
        """Skip integration tests if no API key is configured."""
        if not (os.getenv("WANDB_KEY") or os.getenv("OPENAI_API_KEY")):
            pytest.skip("No API key configured (WANDB_KEY or OPENAI_API_KEY)")

    def test_cli_json_stdin(self, skip_if_no_api_key):
        """PRD: Works via CLI (stdin/stdout) with JSON input."""
        input_json = json.dumps({
            "prompt": "Test CLI input",
            "max_rounds": 1
        })

        result = subprocess.run(
            [sys.executable, "-m", "services.roundtable"],
            input=input_json,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            pytest.fail(f"CLI failed: {result.stderr}")

        output = json.loads(result.stdout)
        assert "transcript" in output
        assert "summary" in output

    def test_cli_usage_without_input(self):
        """CLI should show usage when no input provided."""
        result = subprocess.run(
            [sys.executable, "-m", "services.roundtable"],
            capture_output=True,
            text=True,
            timeout=10,
            input=""  # Empty stdin
        )

        # Should exit with error and show usage
        assert result.returncode == 1
        assert "Usage:" in result.stderr


# ============================================================================
# PRD Acceptance Criteria Checklist Tests
# ============================================================================

class TestAcceptanceCriteria:
    """
    PRD Acceptance Criteria:
    - [ ] Runs 3-agent debate (ARTIST, BUSINESS, TECH)
    - [ ] Each agent has distinct persona
    - [ ] Debate runs for 3 rounds
    - [ ] Agents respond to each other (not just the prompt)
    - [ ] Summarizer produces 3-5 actionable tasks
    - [ ] Works via CLI (stdin/stdout)
    - [ ] Can include context and learnings
    - [ ] Returns structured output (transcript + summary)
    - [ ] Handles LLM errors gracefully
    """

    def test_ac_three_agent_debate(self):
        """AC: Runs 3-agent debate (ARTIST, BUSINESS, TECH)."""
        assert len(ROLES) == 3
        assert set(ROLES) == {"artist", "business", "tech"}

    def test_ac_distinct_personas(self):
        """AC: Each agent has distinct persona."""
        personas = {role: get_persona(role) for role in ROLES}
        # All should be unique
        assert len(set(personas.values())) == 3

    def test_ac_default_three_rounds(self):
        """AC: Debate runs for 3 rounds."""
        import inspect
        sig = inspect.signature(run_roundtable)
        assert sig.parameters["max_rounds"].default == 3

    def test_ac_context_and_learnings(self):
        """AC: Can include context and learnings."""
        import inspect
        sig = inspect.signature(run_roundtable)
        params = sig.parameters
        assert "context" in params
        assert "learnings" in params

    def test_ac_structured_output(self):
        """AC: Returns structured output (transcript + summary)."""
        mock_response = MagicMock()
        mock_response.content = "- Task 1"

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response

        with patch("services.roundtable.runner.get_llm", return_value=mock_llm):
            result = run_roundtable(prompt="Test", max_rounds=1)

        assert "transcript" in result
        assert "summary" in result
        assert isinstance(result["transcript"], str)
        assert isinstance(result["summary"], list)
