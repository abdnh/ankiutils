from typing import Any

from aqt import mw


class Config:
    def __init__(self, module: str) -> None:
        self._module = mw.addonManager.addonFromModule(module)
        self._config = mw.addonManager.getConfig(self._module)
        self._defaults = mw.addonManager.addonConfigDefaults(self._module)
        mw.addonManager.setConfigUpdatedAction(
            self._module, self._config_updated_action
        )

    def _config_updated_action(self, new_config: dict) -> None:
        self._config.update(new_config)

    def _write(self) -> None:
        mw.addonManager.writeConfig(self._module, self._config)

    def __getitem__(self, key: str) -> Any:
        return self._config[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._config[key] = value
        self._write()

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def get_default(self, key: str) -> Any:
        return self._defaults.get(key, None)
