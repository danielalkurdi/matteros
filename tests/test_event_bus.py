"""Tests for the EventBus system."""

from __future__ import annotations

from matteros.core.events import EventBus, EventType, RunEvent


def test_subscribe_and_emit() -> None:
    bus = EventBus()
    received = []
    bus.subscribe(EventType.RUN_STARTED, lambda e: received.append(e))

    event = RunEvent(event_type=EventType.RUN_STARTED, run_id="test-1")
    bus.emit(event)

    assert len(received) == 1
    assert received[0].run_id == "test-1"


def test_wildcard_subscriber_receives_all() -> None:
    bus = EventBus()
    received = []
    bus.subscribe(None, lambda e: received.append(e))

    bus.emit(RunEvent(event_type=EventType.RUN_STARTED, run_id="r1"))
    bus.emit(RunEvent(event_type=EventType.STEP_STARTED, run_id="r1", step_id="s1"))
    bus.emit(RunEvent(event_type=EventType.RUN_COMPLETED, run_id="r1"))

    assert len(received) == 3


def test_unsubscribe() -> None:
    bus = EventBus()
    received = []
    handler = lambda e: received.append(e)

    bus.subscribe(EventType.RUN_STARTED, handler)
    bus.emit(RunEvent(event_type=EventType.RUN_STARTED, run_id="r1"))
    assert len(received) == 1

    bus.unsubscribe(EventType.RUN_STARTED, handler)
    bus.emit(RunEvent(event_type=EventType.RUN_STARTED, run_id="r2"))
    assert len(received) == 1


def test_handler_exception_does_not_propagate() -> None:
    bus = EventBus()
    good_received = []

    def bad_handler(e):
        raise RuntimeError("boom")

    bus.subscribe(EventType.RUN_STARTED, bad_handler)
    bus.subscribe(EventType.RUN_STARTED, lambda e: good_received.append(e))

    bus.emit(RunEvent(event_type=EventType.RUN_STARTED, run_id="r1"))
    assert len(good_received) == 1


def test_clear_removes_all_handlers() -> None:
    bus = EventBus()
    received = []
    bus.subscribe(None, lambda e: received.append(e))
    bus.clear()

    bus.emit(RunEvent(event_type=EventType.RUN_STARTED, run_id="r1"))
    assert len(received) == 0


def test_event_data_preserved() -> None:
    bus = EventBus()
    received = []
    bus.subscribe(EventType.STEP_COMPLETED, lambda e: received.append(e))

    bus.emit(RunEvent(
        event_type=EventType.STEP_COMPLETED,
        run_id="r1",
        step_id="collect_calendar",
        actor="system",
        data={"output_key": "calendar_events"},
    ))

    assert received[0].step_id == "collect_calendar"
    assert received[0].data["output_key"] == "calendar_events"


def test_subscribe_to_draft_created() -> None:
    bus = EventBus()
    received = []
    bus.subscribe(EventType.DRAFT_CREATED, lambda e: received.append(e))

    bus.emit(RunEvent(
        event_type=EventType.DRAFT_CREATED,
        run_id="r1",
        data={"draft_id": "d1"},
    ))
    assert len(received) == 1
    assert received[0].data["draft_id"] == "d1"


def test_subscribe_to_pattern_learned() -> None:
    bus = EventBus()
    received = []
    bus.subscribe(EventType.PATTERN_LEARNED, lambda e: received.append(e))

    bus.emit(RunEvent(
        event_type=EventType.PATTERN_LEARNED,
        run_id="r1",
        data={"pattern_id": "p1", "pattern_type": "matter_assignment"},
    ))
    assert len(received) == 1
    assert received[0].data["pattern_type"] == "matter_assignment"
