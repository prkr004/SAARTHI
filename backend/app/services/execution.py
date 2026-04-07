"""Execution helpers for bounded runtime calls."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Callable, TypeVar

T = TypeVar("T")


_EXECUTOR = ThreadPoolExecutor(max_workers=4)


def run_with_timeout(fn: Callable[..., T], timeout_seconds: int, *args: Any, **kwargs: Any) -> T:
    """Run blocking work with a timeout and raise TimeoutError on expiry."""

    future = _EXECUTOR.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        future.cancel()
        raise TimeoutError(f"Operation exceeded timeout of {timeout_seconds}s") from exc
