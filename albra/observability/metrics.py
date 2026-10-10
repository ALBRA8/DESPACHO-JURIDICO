"""
Métricas simples - contador, gauge, histograma en memoria.

Para producción, integrar con Prometheus/OpenTelemetry.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Any


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._start_time = time.time()

    def inc(self, name: str, value: float = 1.0) -> None:
        self._counters[name] += value

    def set_gauge(self, name: str, value: float) -> None:
        self._gauges[name] = value

    def observe(self, name: str, value: float) -> None:
        self._histograms[name].append(value)

    def time_call(self, name: str):
        """Context manager para medir duración."""
        import contextlib

        @contextlib.contextmanager
        def _ctx():
            t0 = time.perf_counter()
            try:
                yield
            finally:
                self.observe(name + ".duration_s", time.perf_counter() - t0)

        return _ctx()

    def snapshot(self) -> dict[str, Any]:
        return {
            "uptime_s": time.time() - self._start_time,
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms_count": {k: len(v) for k, v in self._histograms.items()},
            "histograms_p95": {
                k: (sorted(v)[int(len(v) * 0.95)] if len(v) > 0 else 0.0)
                for k, v in self._histograms.items()
            },
        }


_metrics: MetricsRegistry | None = None


def get_metrics() -> MetricsRegistry:
    global _metrics
    if _metrics is None:
        _metrics = MetricsRegistry()
    return _metrics
