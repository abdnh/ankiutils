import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from anki.hooks import wrap
from aqt import mw
from aqt.addons import AddonManager


def get_logger(module: str) -> logging.Logger:
    addon = mw.addonManager.addonFromModule(module)
    logger = logging.getLogger(addon)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    stdout_handler.setLevel(logging.DEBUG if "ANKIDEV" in os.environ else logging.INFO)
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    logs_dir = Path(mw.addonManager.addonsFolder(addon)) / "user_files" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = os.path.join(logs_dir, f"{addon}.log")
    file_handler = RotatingFileHandler(
        log_path, "a", encoding="utf-8", maxBytes=3 * 1024 * 1024, backupCount=5
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Prevent errors when deleting/updating the add-on on Windows
    def on_addon_manager_will_delete_addon(
        manager: AddonManager, m: str, *args: Any, **kwargs: Any
    ) -> None:
        if m == addon:
            file_handler.close()

    AddonManager.deleteAddon = wrap(  # type: ignore[method-assign]
        AddonManager.deleteAddon, on_addon_manager_will_delete_addon, "before"
    )

    return logger
