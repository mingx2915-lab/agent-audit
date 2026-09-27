from datetime import datetime, timezone

from agent_audit_api.trace import TraceCollector


def test_trace_collector_assigns_continuous_sequence_and_preserves_order() -> None:
    collector = TraceCollector()

    first = collector.record("input", "Received query", {"message": "hello"})
    second = collector.record("source", "User input source", {"sourceId": "input_1"})
    third = collector.record("sink", "Actor response", {"sinkId": "actor_response"})

    assert [event.sequence for event in collector.snapshot()] == [1, 2, 3]
    assert [event.type for event in collector.snapshot()] == [
        "input",
        "source",
        "sink",
    ]
    assert [first.summary, second.summary, third.summary] == [
        "Received query",
        "User input source",
        "Actor response",
    ]
    for event in collector.snapshot():
        assert event.occurred_at.endswith("Z")
        assert datetime.fromisoformat(
            event.occurred_at.replace("Z", "+00:00")
        ).tzinfo == timezone.utc


def test_trace_collector_snapshot_is_a_new_ordered_list() -> None:
    collector = TraceCollector()
    collector.record("input", "Received query", {})

    first_snapshot = collector.snapshot()
    second_snapshot = collector.snapshot()

    assert first_snapshot == second_snapshot
    assert first_snapshot is not second_snapshot
    first_snapshot.append(first_snapshot[0])
    assert len(collector.snapshot()) == 1


def test_independent_trace_collectors_do_not_share_sequence_state() -> None:
    first = TraceCollector()
    second = TraceCollector()

    first.record("input", "First request", {})
    first.record("sink", "First response", {})
    second_event = second.record("input", "Second request", {})

    assert second_event.sequence == 1
    assert [event.sequence for event in second.snapshot()] == [1]
