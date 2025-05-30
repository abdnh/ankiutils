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


def _read_version(addon_dir: Path) -> str:
    with open(addon_dir / ".version", encoding="utf-8") as f:
        return f.read().strip()


def read_manifest(addon_dir: Path) -> dict[str, Any]:
    with open(addon_dir / "manifest.json", encoding="utf-8") as file:
        return json.load(file)


def _get_manifest_name(addon_dir: Path) -> str | None:
    try:
        return read_manifest(addon_dir)["name"]
    except Exception:
        return None


def get_consts(module: str) -> AddonConsts:
    if is_testing():
        return AddonConsts("addon", "addon", Path.cwd() / "src", "0.0.1")
    meta = mw.addonManager.addon_meta(mw.addonManager.addonFromModule(module))
    module = meta.dir_name
    addon_dir = Path(mw.addonManager.addonsFolder(module))
    name = _get_manifest_name(addon_dir) or meta.human_name()
    return AddonConsts(name, module, addon_dir, _read_version(addon_dir))
