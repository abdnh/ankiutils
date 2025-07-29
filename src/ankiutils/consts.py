from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aqt import mw

from ._internal import is_testing


@dataclass
class AddonConsts:
    name: str
    module: str
    dir: Path
    version: str
    ankiweb_id: str | None


def _read_version(addon_dir: Path) -> str:
    with open(addon_dir / ".version", encoding="utf-8") as f:
        return f.read().strip()


def read_manifest(addon_dir: Path) -> dict[str, Any]:
    with open(addon_dir / "manifest.json", encoding="utf-8") as file:
        return json.load(file)


def _get_manifest_name(manifest: dict[str, Any]) -> str | None:
    try:
        return manifest["name"]
    except Exception:
        return None


def _get_ankiweb_id(manifest: dict[str, Any]) -> str | None:
    try:
        return manifest["ankiweb_id"]
    except Exception:
        return None


def get_consts(module: str) -> AddonConsts:
    if is_testing():
        return AddonConsts("addon", "addon", Path.cwd() / "src", "0.0.1", None)
    meta = mw.addonManager.addon_meta(mw.addonManager.addonFromModule(module))
    module = meta.dir_name
    addon_dir = Path(mw.addonManager.addonsFolder(module))
    manifest = read_manifest(addon_dir)
    name = _get_manifest_name(manifest) or meta.human_name()
    ankiweb_id = _get_ankiweb_id(manifest)
    return AddonConsts(name, module, addon_dir, _read_version(addon_dir), ankiweb_id)
