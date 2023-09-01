from typing import Any

from aqt import mw

from .consts import ADDON_MODULE


class Config:
    def __init__(self) -> None:
        self._config = mw.addonManager.getConfig(ADDON_MODULE)
        self._defaults = mw.addonManager.addonConfigDefaults(ADDON_MODULE)
        mw.addonManager.setConfigUpdatedAction(
            ADDON_MODULE, self._config_updated_action
        )

    def _config_updated_action(self, new_config: dict) -> None:
        self._config.update(new_config)

    def _write(self) -> None:
        mw.addonManager.writeConfig(__name__, self._config)

    def __getitem__(self, key: str) -> Any:
        return self._config[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._config[key] = value
        self._write()

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def get_default(self, key: str) -> Any:
        return self._defaults.get(key, None)
