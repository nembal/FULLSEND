"""Unit tests for the retry module."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from services.watcher.retry import ModelCallError, retry_model_call, with_retry


class TestModelCallError:
    """Tests for ModelCallError exception."""

    def test_error_attributes(self):
        """Test that error has correct attributes."""
        original_error = ValueError("API limit exceeded")
        error = ModelCallError(
            message="Model call failed",
            attempts=3,
            last_error=original_error,
        )

        assert error.message == "Model call failed"
        assert error.attempts == 3
        assert error.last_error == original_error

    def test_error_string(self):
        """Test error string representation."""
        original_error = ValueError("API limit exceeded")
        error = ModelCallError(
            message="Model call failed",
            attempts=3,
            last_error=original_error,
        )

        error_str = str(error)
        assert "Model call failed" in error_str
        assert "3 attempts" in error_str
        assert "API limit exceeded" in error_str


class TestRetryModelCall:
    """Tests for retry_model_call function."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        """Test that successful calls return immediately."""
        async def mock_func():
            return "success"

        result = await retry_model_call(mock_func, max_attempts=3)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_success_after_retry(self):
        """Test that function succeeds after initial failure."""
        call_count = 0

        async def mock_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Temporary error")
            return "success"

        result = await retry_model_call(
            mock_func,
            max_attempts=3,
            base_delay=0.01,  # Fast for testing
        )
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts(self):
        """Test that ModelCallError is raised after all retries fail."""
        call_count = 0

        async def mock_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Persistent error")

        with pytest.raises(ModelCallError) as exc_info:
            await retry_model_call(
                mock_func,
                max_attempts=3,
                base_delay=0.01,
            )

        assert exc_info.value.attempts == 3
        assert "Persistent error" in str(exc_info.value.last_error)
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """Test that delays increase exponentially."""
        delays = []
        call_count = 0

        async def mock_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Error")

        # Patch asyncio.sleep to capture delays
        original_sleep = asyncio.sleep

        async def mock_sleep(delay):
            delays.append(delay)
            await original_sleep(0.001)  # Actually sleep a tiny bit

        import services.watcher.retry as retry_module
        original_asyncio_sleep = retry_module.asyncio.sleep
        retry_module.asyncio.sleep = mock_sleep

        try:
            with pytest.raises(ModelCallError):
                await retry_model_call(
                    mock_func,
                    max_attempts=4,
                    base_delay=1.0,
                    max_delay=10.0,
                )
        finally:
            retry_module.asyncio.sleep = original_asyncio_sleep

        # Should have 3 delays (between 4 attempts)
        assert len(delays) == 3
        # Delays should be 1.0, 2.0, 4.0 (exponential backoff)
        assert delays[0] == 1.0
        assert delays[1] == 2.0
        assert delays[2] == 4.0

    @pytest.mark.asyncio
    async def test_max_delay_cap(self):
        """Test that delays are capped at max_delay."""
        delays = []
        call_count = 0

        async def mock_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Error")

        import services.watcher.retry as retry_module
        original_asyncio_sleep = retry_module.asyncio.sleep

        async def mock_sleep(delay):
            delays.append(delay)
            await original_asyncio_sleep(0.001)  # Use original sleep to avoid recursion

        retry_module.asyncio.sleep = mock_sleep

        try:
            with pytest.raises(ModelCallError):
                await retry_model_call(
                    mock_func,
                    max_attempts=5,
                    base_delay=2.0,
                    max_delay=5.0,  # Cap at 5 seconds
                )
        finally:
            retry_module.asyncio.sleep = original_asyncio_sleep

        # Delays: 2, 4, 5 (capped), 5 (capped)
        assert delays[-1] == 5.0  # Should be capped at max_delay

    @pytest.mark.asyncio
    async def test_passes_args_and_kwargs(self):
        """Test that arguments are passed correctly to the function."""
        received_args = []
        received_kwargs = {}

        async def mock_func(*args, **kwargs):
            received_args.extend(args)
            received_kwargs.update(kwargs)
            return "success"

        result = await retry_model_call(
            mock_func,
            "arg1",
            "arg2",
            key1="value1",
            key2="value2",
            max_attempts=3,
        )

        assert result == "success"
        assert received_args == ["arg1", "arg2"]
        assert received_kwargs == {"key1": "value1", "key2": "value2"}

    @pytest.mark.asyncio
    async def test_works_with_sync_function(self):
        """Test that sync functions also work."""
        def sync_func(x, y):
            return x + y

        result = await retry_model_call(sync_func, 2, 3, max_attempts=3)
        assert result == 5

    @pytest.mark.asyncio
    async def test_preserves_last_error(self):
        """Test that the last error is preserved in ModelCallError."""
        errors = ["Error 1", "Error 2", "Error 3"]
        call_count = 0

        async def mock_func():
            nonlocal call_count
            raise ValueError(errors[call_count])
            call_count += 1

        with pytest.raises(ModelCallError) as exc_info:
            await retry_model_call(
                mock_func,
                max_attempts=3,
                base_delay=0.01,
            )

        # The last error should be preserved
        assert "Error" in str(exc_info.value.last_error)


class TestWithRetryDecorator:
    """Tests for with_retry decorator."""

    @pytest.mark.asyncio
    async def test_decorator_basic(self):
        """Test basic decorator usage."""
        call_count = 0

        @with_retry(max_attempts=3, base_delay=0.01)
        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Flaky")
            return "success"

        result = await flaky_func()
        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_decorator_raises_after_attempts(self):
        """Test decorator raises ModelCallError after all attempts."""
        @with_retry(max_attempts=2, base_delay=0.01)
        async def always_fails():
            raise ValueError("Always fails")

        with pytest.raises(ModelCallError) as exc_info:
            await always_fails()

        assert exc_info.value.attempts == 2
