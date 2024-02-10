from __future__ import annotations

from typing import Any

from aqt import mw

from ._internal import is_testing


class BaseConfig:
    def __init__(self, module: str) -> None:
        self._module = module
        self._config: dict[str, Any] = {}
        self._defaults: dict[str, Any] = {}

    def _write(self) -> None:
        pass

    def __getitem__(self, key: str) -> Any:
        return self._config[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._config[key] = value
        self._write()

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def get_default(self, key: str) -> Any:
        return self._defaults.get(key, None)


class AnkiConfig(BaseConfig):
    def __init__(self, module: str) -> None:
        super().__init__(module)
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


Config = BaseConfig if is_testing() else AnkiConfig
