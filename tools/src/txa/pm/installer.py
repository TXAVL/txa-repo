"""Download, verify and silently run an installer described by a TXA build card."""
from __future__ import annotations

import hmac
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from txa.core import config, engines, net, portable, userpath, winos

MAX_DOWNLOAD = 4 * 1024 * 1024 * 1024
EXIT_CODES = {
    0: "success",
    3010: "success - restart required",
    1641: "success - restart initiated by the installer",
    1602: "cancelled by the user",
    1618: "another installation is already in progress",
    1603: "fatal error during installation",
    1633: "this platform is not supported by the package",
    1223: "elevation (UAC) was declined",
}
SUCCESS = {0, 3010, 1641}


class InstallError(Exception):
    pass


def _by_language(candidates: list[dict], language: str) -> dict:
    """Among installers of one CPU, the one built for this display language, else the one without a language."""
    for target in candidates:
        if (target.get("locale") or "").split("-")[0].lower() == language:
            return target
    for target in candidates:
        if not target.get("locale"):
            return target
    for target in candidates:
        if (target.get("locale") or "").lower().startswith("en"):
            return target
    return candidates[0]


def pick_target(build: dict, arch: str | None = None, language: str | None = None) -> dict:
    """The installer for this CPU (``arch`` forces one) and, when a CPU has several, for the PC's display language."""
    groups: dict[str, list[dict]] = {}
    for target in build.get("targets", []):
        groups.setdefault(target["arch"], []).append(target)
    language = (language or config.lang() or winos.ui_language()).split("-")[0].lower()
    if arch:
        if arch not in groups:
            raise InstallError(f"no {arch} installer (available: {', '.join(groups)})")
        return _by_language(groups[arch], language)
    native = winos.native_arch()
    for candidate in winos.arch_preference(native):
        if candidate in groups:
            return _by_language(groups[candidate], language)
    raise InstallError(f"no installer runs on {native} (available: {', '.join(groups)})")


def check_os(build: dict) -> None:
    current = winos.current()
    needed = winos.parse_build(build["platform"]["min_build"])
    if current and current < needed:
        raise InstallError(f"needs Windows {winos.fmt(needed)} ({winos.describe(needed)}), "
                           f"this machine runs {winos.fmt(current)}")


def download_payload(package_id: str, version: str, target: dict, on_progress=None, source=None) -> net.Download:
    """Download into %TEMP%\\txa\\<id>\\<version>\\<arch>. Call verify_payload() before using the file.

    ``source`` (a pm.source.Source) may allow LAN hosts and lend its credentials to its own host.
    """
    dest = config.temp_root() / package_id / version / target["arch"]
    url = target["source"]["url"]
    return net.download(net.session(), url, dest, MAX_DOWNLOAD, on_progress=on_progress,
                        allow_private=bool(source and source.allow_lan),
                        headers=source.download_headers(url) if source else None)


def verify_payload(result: net.Download, target: dict, ignore_checksum: bool = False) -> str:
    """Compare SHA-256 with the manifest; if evergreen vendor updated the binary, check OS Authenticode signature."""
    expected = str(target["source"]["sha256"]).upper()
    if hmac.compare_digest(result.sha256, expected):
        return result.sha256
    if ignore_checksum:
        return result.sha256
    try:
        from txa.core import signing

        sig = signing.verify(result.path)
        if sig.status == "valid" and sig.signer_cn:
            setattr(result, "verified_signer", sig.signer_cn)
            return result.sha256
    except Exception:
        pass
    result.path.unlink(missing_ok=True)
    raise InstallError(f"SHA-256 mismatch - expected {expected}, got {result.sha256}. The file was deleted.")


def fetch(package_id: str, version: str, target: dict, on_progress=None, source=None) -> Path:
    """Download and verify in one call (used by `txapm download`)."""
    result = download_payload(package_id, version, target, on_progress, source)
    verify_payload(result, target)
    return result.path


# --------------------------------------------------------------------------- portable packages


def apps_root() -> Path:
    return config.txa_home() / "apps"


def install_portable(package_id: str, version: str, target: dict, archive: Path, on_progress=None) -> dict:
    """Unpack a portable ZIP into %LOCALAPPDATA%\\TXA\\apps\\<id>\\<version> and put its folders on the user PATH."""
    if sys.platform != "win32":
        raise InstallError("portable packages can only be installed on Windows")
    spec = target["portable"]
    dest = apps_root() / package_id / version
    previous = installed().get(package_id) or {}
    try:
        files = portable.extract(archive, dest, int(spec.get("strip", 0)), on_progress)
    except (portable.ZipProblem, OSError, zipfile.BadZipFile) as exc:
        shutil.rmtree(dest, ignore_errors=True)
        raise InstallError(f"could not unpack the archive: {exc}") from None
    folders = spec["path"]
    for folder in folders:
        target_dir = dest if folder == "." else dest.joinpath(*PurePosixPath(folder).parts)
        for exe_f in target_dir.glob("*-windows-msvc.exe"):
            short_name = exe_f.name.split("-")[0] + ".exe"
            if not (target_dir / short_name).exists():
                try:
                    shutil.copy2(exe_f, target_dir / short_name)
                except OSError:
                    pass
        if not portable.folder_exists_with_exe(dest, folder):
            shutil.rmtree(dest, ignore_errors=True)
            raise InstallError(f"after unpacking, '{folder}' holds no .exe - the manifest's strip/path are wrong")
    dirs = [str(dest if f == "." else dest.joinpath(*PurePosixPath(f).parts)) for f in folders]
    try:
        # one atomic edit: forget this package's older versions, then register the new folders
        userpath.update(add=dirs, drop_under=apps_root() / package_id)
    except OSError as exc:
        raise InstallError(f"unpacked to {dest} but could not update PATH: {exc}") from None
    old_dir = previous.get("dir")
    if old_dir and Path(old_dir) != dest:
        shutil.rmtree(old_dir, ignore_errors=True)
    return {"dir": str(dest), "path_dirs": dirs, "files": files}


def uninstall_portable(package_id: str) -> Path | None:
    """Remove the package's folders from PATH, then delete them. Returns the folder removed."""
    root = apps_root() / package_id
    try:
        userpath.update(drop_under=root)
    except OSError as exc:
        raise InstallError(f"could not update PATH: {exc}") from None
    if not root.exists():
        return None
    shutil.rmtree(root)
    return root


def build_command(target: dict, payload: Path, mode: str, log: Path) -> tuple[str, str]:
    """Return (executable, parameters). mode: silent | progress | interactive."""
    engine = target["engine"]
    is_msi_file = str(payload).lower().endswith(".msi")
    if is_msi_file and engine == "wix":
        engine = "msi"
    switches = engines.effective_switches({**target, "engine": engine})
    chosen = "" if mode == "interactive" else switches[mode]
    parts = [p for p in (chosen, switches["custom"]) if p]
    upper = " ".join(parts).upper()
    if engine == "msi" or is_msi_file:
        params = subprocess.list2cmdline(["/i", str(payload)])
        if mode != "interactive":
            params += f" {' '.join(parts)}"
        params += " " + subprocess.list2cmdline(["/l*v", str(log)])
        return "msiexec.exe", params.strip()
    if engine == "inno" and mode != "interactive" and "/LOG" not in upper:
        parts.append(subprocess.list2cmdline([f"/LOG={log}"]))
    if engine == "wix" and mode != "interactive" and "/LOG" not in upper:
        parts.append(subprocess.list2cmdline(["/log", str(log)]))
    return str(payload), " ".join(parts)


def is_admin() -> bool:
    if sys.platform != "win32":
        return False
    import ctypes

    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def run(executable: str, params: str, elevate: bool) -> int:
    if sys.platform != "win32":
        raise InstallError("installing requires Windows (use --download-only elsewhere)")
    if elevate and not is_admin():
        return _run_elevated(executable, params)
    command = f"{subprocess.list2cmdline([executable])} {params}".strip()
    return subprocess.run(command).returncode  # CreateProcess directly - no shell involved


def _run_elevated(executable: str, params: str) -> int:
    import ctypes
    from ctypes import wintypes

    class ShellExecuteInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
        ]

    see_mask_nocloseprocess, see_mask_noasync = 0x40, 0x100
    info = ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = see_mask_nocloseprocess | see_mask_noasync
    info.lpVerb = "runas"
    info.lpFile = executable
    info.lpParameters = params
    info.nShow = 1
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.windll.kernel32
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(ShellExecuteInfo)]
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        error = ctypes.get_last_error()
        if error == 1223:
            return 1223
        raise InstallError(f"could not start elevated installer (Win32 error {error})")
    kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
    code = wintypes.DWORD()
    kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
    kernel32.CloseHandle(info.hProcess)
    return code.value


# --------------------------------------------------------------------------- local records


def _records_path() -> Path:
    return config.txa_home() / "state" / "installed.json"


def installed() -> dict:
    try:
        return json.loads(_records_path().read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def record(package_id: str, version: str, target: dict, exit_code: int, name: str, scope: str,
           source: str = config.OFFICIAL_SOURCE, extra: dict | None = None) -> None:
    data = installed()
    data[package_id] = {
        "version": version, "arch": target["arch"], "engine": target["engine"], "exit_code": exit_code,
        "name": name, "scope": scope, "source": source, "installed": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **(extra or {}),
    }
    _save(data)


def forget(package_id: str) -> None:
    data = installed()
    data.pop(package_id, None)
    _save(data)


def _pins_path() -> Path:
    return config.txa_home() / "state" / "pins.json"


def pins() -> dict[str, str]:
    """package id -> pinned version ('*' = never upgrade)."""
    try:
        return json.loads(_pins_path().read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def set_pin(package_id: str, version: str | None) -> None:
    data = pins()
    if version is None:
        data.pop(package_id, None)
    else:
        data[package_id] = version
    path = _pins_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), "utf-8")


def _save(data: dict) -> None:
    path = _records_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), "utf-8")
