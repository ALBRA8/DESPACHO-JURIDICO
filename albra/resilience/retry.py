"""Política de retry con backoff exponencial."""
from __future__ import annotations

import asyncio
import functools
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

T = TypeVar("T")


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 10.0
    backoff_factor: float = 2.0
    jitter: bool = True
    exceptions: tuple[type[BaseException], ...] = (Exception,)


def retry(policy: RetryPolicy | None = None) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    p = policy or RetryPolicy()

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            attempt = 0
            delay = p.base_delay
            last_exc: BaseException | None = None
            while attempt < p.max_attempts:
                try:
                    return await fn(*args, **kwargs)
                except p.exceptions as e:
                    last_exc = e
                    attempt += 1
                    if attempt >= p.max_attempts:
                        break
                    sleep = min(delay, p.max_delay)
                    if p.jitter:
                        sleep *= (0.5 + random.random())
                    await asyncio.sleep(sleep)
                    delay *= p.backoff_factor
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator
