"""Opt-in 100-iteration StabilityRunner evidence.

This is intentionally separate from the normal integration contract tests:
set ``AGENT_AUDIT_RUN_STABILITY=1`` when collecting the long workflow soak.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from agent_audit_api.stability import StabilityRunner


pytestmark = pytest.mark.skipif(
    os.environ.get("AGENT_AUDIT_RUN_STABILITY") != "1",
    reason="set AGENT_AUDIT_RUN_STABILITY=1 to run the 100-iteration workflow soak",
)


def test_one_hundred_workflows_have_independent_ids_and_history_observations() -> None:
    evidence = asyncio.run(StabilityRunner(iterations=100, max_rounds=2).run())

    assert evidence.status == "passed"
    assert evidence.checks[0].status == "passed"
    assert evidence.checks[0].iterations == 100
    assert evidence.checks[0].completed_iterations == 100
    assert len(evidence.iterations) == 100
    assert evidence.observations.history_count == 100
    assert evidence.observations.successful_workflows == 100
    assert evidence.observations.replay_pass_count == 100
    assert evidence.observations.finding_count >= 100
    assert evidence.failures == []

    scan_ids = [item.scan_id for item in evidence.iterations]
    replay_ids = [item.replay_id for item in evidence.iterations]
    assert all(scan_ids)
    assert all(replay_ids)
    assert len(set(scan_ids)) == 100
    assert len(set(replay_ids)) == 100

    for index, item in enumerate(evidence.iterations, start=1):
        assert item.iteration == index
        assert item.status == "passed"
        assert item.history_persisted is True
        assert item.history_count == index
        assert item.source_sink_finding is True
        assert item.finding_count >= 1
        assert item.replay_status == "passed"
        assert item.replay_before_evaluation == "failed"
        assert item.replay_after_evaluation == "passed"
        assert item.replay_after_execution == "blocked"
