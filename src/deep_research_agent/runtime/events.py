from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

RuntimeEventEmitter = Callable[[dict[str, Any]], None]

_runtime_event_emitter: ContextVar[RuntimeEventEmitter | None] = ContextVar("runtime_event_emitter", default=None)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def runtime_event_scope(emitter: RuntimeEventEmitter) -> Iterator[None]:
    token = _runtime_event_emitter.set(emitter)
    try:
        yield
    finally:
        _runtime_event_emitter.reset(token)


def emit_runtime_event(event: str, /, **payload: Any) -> None:
    emitter = _runtime_event_emitter.get()
    if emitter is None:
        return
    emitter(
        {
            "event": event,
            "created_at": _utc_now_iso(),
            **payload,
        }
    )