from dataclasses import dataclass
from pathlib import Path

from aqt import mw


@dataclass
class AddonConsts:
    name: str
    module: str
    dir: Path


def get_consts(module: str) -> AddonConsts:
    meta = mw.addonManager.addon_meta(mw.addonManager.addonFromModule(module))
    name = meta.human_name()
    module = meta.dir_name
    dir = Path(mw.addonManager.addonsFolder(module))
    return AddonConsts(name, module, dir)
