"""Scheduling — agents programados o event-driven (V2.4-A)."""
from albra.scheduling.scheduler import (
    ALL_EVENTS,
    ON_APPROVAL_PENDING,
    ON_DEADLINE_NEAR,
    ON_MATTER_CREATED,
    ON_STATE_CHANGE,
    TRIGGER_DAILY_AT,
    TRIGGER_INTERVAL,
    Scheduler,
    Trigger,
)

__all__ = [
    "ALL_EVENTS",
    "ON_APPROVAL_PENDING",
    "ON_DEADLINE_NEAR",
    "ON_MATTER_CREATED",
    "ON_STATE_CHANGE",
    "TRIGGER_DAILY_AT",
    "TRIGGER_INTERVAL",
    "Scheduler",
    "Trigger",
]
