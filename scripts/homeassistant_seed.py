from __future__ import annotations

import argparse
import json
import shutil
import uuid
from pathlib import Path


VOLATILE_FILES = {
    ".ha_run.lock",
    "home-assistant.log",
    "home-assistant.log.1",
    "home-assistant.log.fault",
    "home-assistant_v2.db-shm",
    "home-assistant_v2.db-wal",
}

BROADLINK_DEVICES = {
    "rm4mini": {
        "unique_id": "ec0bae9ea91d",
        "mac": "ec0bae9ea91d",
        "type": 21014,
        "title": "RM4 Mini",
    },
    "rm4pro": {
        "unique_id": "e87072ba6c04",
        "mac": "e87072ba6c04",
        "type": 21003,
        "title": "RM4 Pro",
    },
}

CUSTOM_COMPONENTS_CONTAINER_PATH = Path("/workdir/custom_components")

ROOT_FILE_WHITELIST = {
    ".HA_VERSION",
    "automations.yaml",
    "configuration.yaml",
    "scenes.yaml",
    "scripts.yaml",
    "secrets.yaml",
}

ROOT_DIR_WHITELIST = {
    ".storage",
    "themes",
}

STORAGE_FILE_WHITELIST = {
    "auth",
    "auth_provider.homeassistant",
    "core.area_registry",
    "core.config",
    "core.config_entries",
    "core.device_registry",
    "core.entity_registry",
    "core.restore_state",
    "core.uuid",
    "frontend.system_data",
    "http",
    "http.auth",
    "onboarding",
    "person",
}


def _copytree(seed_dir: Path, target_dir: Path) -> None:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(seed_dir, target_dir)


def _remove_unlisted_children(directory: Path, *, allowed_files: set[str], allowed_dirs: set[str]) -> None:
    if not directory.exists():
        return

    for child in directory.iterdir():
        if child.is_dir():
            if child.name in allowed_dirs:
                continue
            shutil.rmtree(child)
            continue
        if child.name not in allowed_files:
            child.unlink()


def curate_seed(target_dir: Path) -> None:
    _remove_unlisted_children(
        target_dir,
        allowed_files=ROOT_FILE_WHITELIST,
        allowed_dirs=ROOT_DIR_WHITELIST,
    )

    themes_dir = target_dir / "themes"
    themes_dir.mkdir(exist_ok=True)

    storage_dir = target_dir / ".storage"
    storage_dir.mkdir(exist_ok=True)
    _remove_unlisted_children(
        storage_dir,
        allowed_files=STORAGE_FILE_WHITELIST,
        allowed_dirs=set(),
    )

    for filename, empty_content in (
        ("automations.yaml", "[]\n"),
        ("scenes.yaml", ""),
        ("scripts.yaml", ""),
    ):
        file_path = target_dir / filename
        if not file_path.exists():
            file_path.write_text(empty_content)


def _remove_volatile_files(target_dir: Path) -> None:
    for filename in VOLATILE_FILES:
        candidate = target_dir / filename
        if candidate.exists():
            candidate.unlink()


def _symlink_custom_components(target_dir: Path) -> None:
    link_path = target_dir / "custom_components"
    if link_path.exists() or link_path.is_symlink():
        if link_path.is_dir() and not link_path.is_symlink():
            shutil.rmtree(link_path)
        else:
            link_path.unlink()

    link_path.symlink_to(CUSTOM_COMPONENTS_CONTAINER_PATH)


def _rewrite_runtime_uuid(target_dir: Path) -> None:
    uuid_path = target_dir / ".storage" / "core.uuid"
    if not uuid_path.exists():
        return

    payload = json.loads(uuid_path.read_text())
    payload.setdefault("data", {})["uuid"] = uuid.uuid4().hex
    uuid_path.write_text(json.dumps(payload, indent=2) + "\n")


def _finalize_runtime(target_dir: Path) -> None:
    curate_seed(target_dir)
    _remove_volatile_files(target_dir)
    _rewrite_runtime_uuid(target_dir)
    _symlink_custom_components(target_dir)


def _load_config_entries(target_dir: Path) -> dict:
    config_entries_path = target_dir / ".storage" / "core.config_entries"
    if not config_entries_path.exists():
        raise FileNotFoundError(f"Missing Home Assistant config entries file: {config_entries_path}")
    return json.loads(config_entries_path.read_text())


def _write_config_entries(target_dir: Path, payload: dict) -> None:
    config_entries_path = target_dir / ".storage" / "core.config_entries"
    config_entries_path.write_text(json.dumps(payload, indent=2) + "\n")


def sync_seed(seed_dir: Path, target_dir: Path, *, clean: bool) -> None:
    if not seed_dir.exists():
        raise FileNotFoundError(f"Seed directory does not exist: {seed_dir}")
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    if clean and target_dir.exists():
        shutil.rmtree(target_dir)
    _copytree(seed_dir, target_dir)
    _finalize_runtime(target_dir)


def patch_broadlink_hosts(
    target_dir: Path,
    *,
    rm4mini_ip: str | None,
    rm4pro_ip: str | None,
) -> bool:
    updates = {
        "rm4mini": (rm4mini_ip or "").strip(),
        "rm4pro": (rm4pro_ip or "").strip(),
    }
    requested_updates = {key: value for key, value in updates.items() if value}
    if not requested_updates:
        return False

    payload = _load_config_entries(target_dir)
    entries = payload.setdefault("data", {}).setdefault("entries", [])

    for device_key, host in requested_updates.items():
        metadata = BROADLINK_DEVICES[device_key]
        for entry in entries:
            if entry.get("domain") != "broadlink":
                continue
            if entry.get("unique_id") not in {metadata["unique_id"], metadata["mac"]}:
                continue
            entry.setdefault("data", {})["host"] = host
            entry["data"]["mac"] = metadata["mac"]
            entry["data"]["type"] = metadata["type"]
            entry["title"] = metadata["title"]
            break
        else:
            raise RuntimeError(
                f"Broadlink entry '{device_key}' was not found in {target_dir / '.storage' / 'core.config_entries'}"
            )

    _write_config_entries(target_dir, payload)
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the committed Home Assistant seed.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="Copy the committed seed into a runtime directory.")
    sync_parser.add_argument("--seed", required=True, type=Path)
    sync_parser.add_argument("--target", required=True, type=Path)
    sync_parser.add_argument("--clean", action="store_true")

    patch_parser = subparsers.add_parser(
        "patch-broadlink",
        help="Override Broadlink IPs in a Home Assistant runtime.",
    )
    patch_parser.add_argument("--target", required=True, type=Path)
    patch_parser.add_argument("--rm4-mini-ip", default="")
    patch_parser.add_argument("--rm4-pro-ip", default="")

    curate_parser = subparsers.add_parser(
        "curate",
        help="Trim a seed/runtime directory down to the minimal committed subset.",
    )
    curate_parser.add_argument("--target", required=True, type=Path)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "sync":
        sync_seed(args.seed, args.target, clean=args.clean)
        return 0

    if args.command == "patch-broadlink":
        patch_broadlink_hosts(
            args.target,
            rm4mini_ip=args.rm4_mini_ip,
            rm4pro_ip=args.rm4_pro_ip,
        )
        return 0

    if args.command == "curate":
        curate_seed(args.target)
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
