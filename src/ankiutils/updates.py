from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import IO, Any, Callable
from zipfile import ZipFile

from anki.hooks import wrap
from anki.utils import is_win, point_version
from aqt import mw
from aqt.addons import AddonManager, InstallError, InstallOk
from aqt.utils import ask_user, send_to_trash

from .config import Config
from .consts import AddonConsts


def anki_path() -> Path:
    if point_version() >= 250700:
        from aqt.package import launcher_executable  # type: ignore # noqa: PLC0415

        return Path(launcher_executable())
    return Path(sys.argv[0])


def is_our_addon_module(consts: AddonConsts, module: str) -> bool:
    base_name, _, _hash = module.partition("-")
    return base_name in (consts.module, consts.ankiweb_id)


def get_updates_dir(consts: AddonConsts) -> Path:
    updates_dir = consts.dir.parent / f"_{consts.module}_updates"
    updates_dir.mkdir(parents=True, exist_ok=True)
    return updates_dir


def run_restart_anki_script(consts: AddonConsts, *args: Any) -> None:
    pid = os.getpid()
    updates_dir = get_updates_dir(consts)
    shutil.copytree(consts.dir / "bin" / "restart_anki", updates_dir / "restart_anki")
    exe_path = updates_dir / "restart_anki" / "restart_anki.exe"
    anki_exe = anki_path()
    anki_base = mw.pm.base
    subprocess.Popen([str(exe_path), str(pid), anki_exe, anki_base, *args])


def prompt_restart_and_install(
    consts: AddonConsts, config: Config, package_path: str
) -> None:
    def on_result(result: bool) -> None:
        if result:
            config["first_run"] = True
            run_restart_anki_script(consts, package_path)
            mw.close()

    ask_user(
        "To complete the update, Anki needs to restart. "
        "Click OK to restart now and finish installing the add-on.",
        title=f"{consts.name} - Restart Required",
        defaults_yes=True,
        callback=on_result,
    )


package_path_or_buffer: IO | str | None = None


def install_addon(
    self: AddonManager,
    file: IO | str,
    manifest: dict[str, Any] | None,
    force_enable: bool,
    _old: Callable,
) -> InstallOk | InstallError:
    global package_path_or_buffer
    package_path_or_buffer = file

    return _old(self, file, manifest, force_enable)


def _install_addon(
    self: AddonManager,
    module: str,
    zfile: ZipFile,
    consts: AddonConsts,
    config: Config,
    _old: Callable,
) -> None:
    if not is_our_addon_module(consts, module):
        return _old(self, module, zfile)

    updates_dir = get_updates_dir(consts)
    out_path = updates_dir / f"{consts.module}.ankiaddon"
    zipdata: bytes | None = None
    if isinstance(package_path_or_buffer, str):
        with open(package_path_or_buffer, "rb") as in_f:
            zipdata = in_f.read()
    else:
        package_path_or_buffer.seek(0, os.SEEK_SET)
        zipdata = package_path_or_buffer.read()
    with open(out_path, "wb") as out_f:
        out_f.write(zipdata)

    def on_main() -> None:
        mw.progress.clear()
        prompt_restart_and_install(consts, config, str(out_path))

    mw.taskman.run_on_main(on_main)


def delete_addon(
    self: AddonManager,
    module: str,
    consts: AddonConsts,
    config: Config,
    _old: Callable,
) -> None:
    if is_our_addon_module(consts, module):
        addon_dir = self.addonsFolder(module)
        run_restart_anki_script(consts, addon_dir)
        mw.close()
    else:
        _old(self, module)


def clean_up_update_packages(consts: AddonConsts) -> None:
    updates_dir = get_updates_dir(consts)
    for path in updates_dir.iterdir():
        send_to_trash(path)


def init_hooks(consts: AddonConsts, config: Config) -> None:
    """Hook Anki's AddonManager to require a restart for add-on updates on Windows. \
    Intended to work around permission issues with add-ons \
    that rely on C extension modules."""

    if is_win:
        clean_up_update_packages(consts)
        AddonManager.install = wrap(AddonManager.install, install_addon, "around")  # type: ignore[method-assign]
        AddonManager._install = wrap(  # type: ignore[method-assign]
            AddonManager._install,
            functools.partial(_install_addon, consts=consts, config=config),
            "around",
        )
        AddonManager.deleteAddon = wrap(  # type: ignore[method-assign]
            AddonManager.deleteAddon,
            functools.partial(delete_addon, consts=consts, config=config),
            "around",
        )
