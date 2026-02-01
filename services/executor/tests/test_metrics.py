"""Unit tests for the metrics module.

Tests timeout and retry logic with:
- Timeout handling (ToolTimeoutError)
- Retry with exponential backoff for transient errors
- Non-transient errors are not retried
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.executor.loader import ToolRetryExhaustedError, ToolTimeoutError
from services.executor.metrics import (
    execute_with_retry,
    execute_with_timeout,
)


class TestExecuteWithTimeout:
    """Tests for execute_with_timeout function."""

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Test successful tool execution within timeout."""
        def fast_tool():
            return {"status": "ok"}

        result = await execute_with_timeout(fast_tool, timeout=5)

        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_timeout_raises_error(self):
        """Test that slow tool raises ToolTimeoutError."""
        def slow_tool():
            import time
            time.sleep(2)
            return {"status": "ok"}

        with pytest.raises(ToolTimeoutError) as exc_info:
            await execute_with_timeout(slow_tool, timeout=1)

        assert "exceeded" in str(exc_info.value).lower()
        assert "1s timeout" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_timeout_value_in_error_message(self):
        """Test that timeout value appears in error message."""
        def slow_tool():
            import time
            time.sleep(1)
            return {}

        with pytest.raises(ToolTimeoutError) as exc_info:
            await execute_with_timeout(slow_tool, timeout=0.1)

        assert "0.1s" in str(exc_info.value)


class TestExecuteWithRetry:
    """Tests for execute_with_retry function."""

    @pytest.mark.asyncio
    async def test_successful_first_attempt(self):
        """Test successful execution on first attempt."""
        call_count = 0

        def success_tool():
            nonlocal call_count
            call_count += 1
            return {"success": True}

        result = await execute_with_retry(
            success_tool,
            timeout=5,
            max_attempts=3,
            backoff_min=0.01,
            backoff_max=0.1,
        )

        assert result == {"success": True}
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_connection_error(self):
        """Test retry on ConnectionError (transient)."""
        call_count = 0

        def flaky_tool():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Connection reset")
            return {"success": True}

        result = await execute_with_retry(
            flaky_tool,
            timeout=5,
            max_attempts=3,
            backoff_min=0.01,
            backoff_max=0.1,
        )

        assert result == {"success": True}
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted_error(self):
        """Test ToolRetryExhaustedError when all attempts fail."""
        call_count = 0

        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Always fails")

        with pytest.raises(ToolRetryExhaustedError) as exc_info:
            await execute_with_retry(
                always_fails,
                timeout=5,
                max_attempts=3,
                backoff_min=0.01,
                backoff_max=0.1,
            )

        assert exc_info.value.attempts == 3
        assert isinstance(exc_info.value.last_error, ConnectionError)
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_value_error(self):
        """Test that non-transient errors are not retried."""
        call_count = 0

        def bad_params():
            nonlocal call_count
            call_count += 1
            raise ValueError("Invalid parameter")

        with pytest.raises(ValueError):
            await execute_with_retry(
                bad_params,
                timeout=5,
                max_attempts=3,
                backoff_min=0.01,
                backoff_max=0.1,
            )

        # Should only be called once since ValueError is not transient
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_tool_timeout(self):
        """Test that ToolTimeoutError is not retried."""
        call_count = 0

        def very_slow():
            nonlocal call_count
            call_count += 1
            import time
            time.sleep(2)
            return {}

        with pytest.raises(ToolTimeoutError):
            await execute_with_retry(
                very_slow,
                timeout=0.1,
                max_attempts=3,
                backoff_min=0.01,
                backoff_max=0.1,
            )

        # Should only be called once since timeouts are not retried
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_os_error(self):
        """Test retry on OSError (transient)."""
        call_count = 0

        def network_issue():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise OSError("Network unreachable")
            return {"recovered": True}

        result = await execute_with_retry(
            network_issue,
            timeout=5,
            max_attempts=3,
            backoff_min=0.01,
            backoff_max=0.1,
        )

        assert result == {"recovered": True}
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_io_error(self):
        """Test retry on IOError (transient)."""
        call_count = 0

        def io_issue():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise IOError("I/O error")
            return {"recovered": True}

        result = await execute_with_retry(
            io_issue,
            timeout=5,
            max_attempts=3,
            backoff_min=0.01,
            backoff_max=0.1,
        )

        assert result == {"recovered": True}
        assert call_count == 2
