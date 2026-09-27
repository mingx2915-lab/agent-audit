"""Synchronize every AgentAudit product version field from one SemVer value."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def load_json(root: Path, relative: str) -> dict:
    value = json.loads((root / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{relative} must contain a JSON object")
    return value


def write_json(root: Path, relative: str, value: dict) -> None:
    (root / relative).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def replace_one(root: Path, relative: str, pattern: str, version: str) -> None:
    path = root / relative
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(
        pattern,
        rf"\g<1>{version}\g<2>",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise ValueError(f"unable to update product version in {relative}")
    path.write_text(updated, encoding="utf-8")


def synchronize(root: Path, version: str) -> None:
    if not SEMVER.fullmatch(version):
        raise ValueError("version must be a valid SemVer value")
    root_package = load_json(root, "package.json")
    package_lock = load_json(root, "package-lock.json")
    desktop_package = load_json(root, "apps/desktop/package.json")
    tauri_config = load_json(root, "apps/desktop/src-tauri/tauri.conf.json")
    packages = package_lock.get("packages")
    if not isinstance(packages, dict) or not isinstance(packages.get(""), dict):
        raise ValueError("package-lock.json is missing the root workspace entry")
    if not isinstance(packages.get("apps/desktop"), dict):
        raise ValueError("package-lock.json is missing the apps/desktop workspace entry")

    cargo_manifest = (root / "apps/desktop/src-tauri/Cargo.toml").read_text(
        encoding="utf-8"
    )
    cargo_lock = (root / "apps/desktop/src-tauri/Cargo.lock").read_text(
        encoding="utf-8"
    )
    api_manifest = (root / "apps/api/pyproject.toml").read_text(encoding="utf-8")
    manifest_match = re.search(
        r'^\[package\]\r?\nname\s*=\s*"agent-audit-desktop"\r?\nversion\s*=\s*"([^"]+)"',
        cargo_manifest,
        flags=re.MULTILINE,
    )
    lock_match = re.search(
        r'^\[\[package\]\]\r?\nname\s*=\s*"agent-audit-desktop"\r?\nversion\s*=\s*"([^"]+)"',
        cargo_lock,
        flags=re.MULTILINE,
    )
    if manifest_match is None or lock_match is None:
        raise ValueError("unable to read current Cargo product versions")
    api_match = re.search(
        r'^\[project\]\r?\nname\s*=\s*"agent-audit-api"\r?\nversion\s*=\s*"([^"]+)"',
        api_manifest,
        flags=re.MULTILINE,
    )
    if api_match is None:
        raise ValueError("unable to read current API product version")
    current_versions = {
        root_package.get("version"),
        package_lock.get("version"),
        packages[""].get("version"),
        desktop_package.get("version"),
        packages["apps/desktop"].get("version"),
        tauri_config.get("version"),
        manifest_match.group(1),
        lock_match.group(1),
        api_match.group(1),
    }
    if len(current_versions) != 1 or not all(
        isinstance(current, str) and current for current in current_versions
    ):
        raise ValueError("current AgentAudit product versions are inconsistent")

    root_package["version"] = version
    desktop_package["version"] = version
    tauri_config["version"] = version
    package_lock["version"] = version
    packages[""]["version"] = version
    packages["apps/desktop"]["version"] = version
    write_json(root, "package.json", root_package)
    write_json(root, "package-lock.json", package_lock)
    write_json(root, "apps/desktop/package.json", desktop_package)
    write_json(root, "apps/desktop/src-tauri/tauri.conf.json", tauri_config)
    replace_one(
        root,
        "apps/desktop/src-tauri/Cargo.toml",
        r'(^\[package\]\r?\nname\s*=\s*"agent-audit-desktop"\r?\nversion\s*=\s*")[^"]+("\s*$)',
        version,
    )
    replace_one(
        root,
        "apps/desktop/src-tauri/Cargo.lock",
        r'(^\[\[package\]\]\r?\nname\s*=\s*"agent-audit-desktop"\r?\nversion\s*=\s*")[^"]+("\s*$)',
        version,
    )
    replace_one(
        root,
        "apps/api/pyproject.toml",
        r'(^\[project\]\r?\nname\s*=\s*"agent-audit-api"\r?\nversion\s*=\s*")[^"]+("\s*$)',
        version,
    )


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    synchronize(args.root.resolve(strict=True), args.version)
    print(f"AgentAudit product version synchronized to {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
