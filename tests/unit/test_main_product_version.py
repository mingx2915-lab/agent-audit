from __future__ import annotations

import agent_audit_api.main as main_module


def test_product_version_uses_installed_metadata_for_shallow_frozen_module(
    monkeypatch,
) -> None:
    class ShallowResolvedPath:
        @property
        def parents(self):
            return ()

        def resolve(self):
            return self

    monkeypatch.setattr(main_module, "Path", lambda *_args: ShallowResolvedPath())
    monkeypatch.setattr(
        main_module,
        "package_version",
        lambda package_name: "0.1.2" if package_name == "agent-audit-api" else None,
    )

    assert main_module._product_version() == "0.1.2"
