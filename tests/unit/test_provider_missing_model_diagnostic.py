"""Regression coverage for Provider 404 diagnostics during readiness/execution."""

import pytest

from agent_audit_api.provider_diagnostics import provider_error_diagnostic


@pytest.mark.parametrize("stage", ["readiness", "execution"])
def test_provider_404_diagnostic_mentions_model_and_does_not_blame_only_base_url(
    stage: str,
) -> None:
    diagnostic = provider_error_diagnostic(
        RuntimeError("synthetic provider 404"),
        stage=stage,
        provider_kind="openai_compatible",
        status_code=404,
    )

    assert "HTTP 404" in diagnostic
    assert "\u6a21\u578b\u540d\u79f0" in diagnostic
    assert "服务地址" in diagnostic
    assert "\u8bf7\u786e\u8ba4\u586b\u5199\u7684\u662f\u670d\u52a1\u5730\u5740" not in diagnostic
