"""Cadena de fallback - si A falla, intentar B, etc."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class FallbackChain:
    """Ejecuta callables en orden hasta que uno tenga éxito."""

    def __init__(self) -> None:
        self._chain: list[tuple[str, Callable[..., Awaitable[Any]]]] = []

    def add(self, name: str, fn: Callable[..., Awaitable[Any]]) -> None:
        self._chain.append((name, fn))

    async def execute(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        errors: list[dict[str, Any]] = []
        for name, fn in self._chain:
            try:
                result = await fn(*args, **kwargs)
                return {"ok": True, "provider": name, "result": result, "errors": errors}
            except Exception as e:  # noqa: BLE001
                errors.append({"provider": name, "error": str(e)})
        return {"ok": False, "errors": errors}
