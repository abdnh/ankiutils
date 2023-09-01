from pathlib import Path

from aqt import mw

META = mw.addonManager.addon_meta(mw.addonManager.addonFromModule(__name__))
ADDON_NAME = META.human_name
ADDON_MODULE = META.dir_name
ADDON_DIR = Path(mw.addonManager.addonsFolder(ADDON_MODULE))
