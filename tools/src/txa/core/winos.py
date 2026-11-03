"""Windows build table, current OS version and native CPU architecture."""
from __future__ import annotations

import os
import sys

# GA builds TXA knows about. Keep sorted; the last entry is the newest GA build.
BUILDS: dict[tuple[int, int, int], str] = {
    (6, 1, 7601): "Windows 7 SP1",
    (6, 2, 9200): "Windows 8",
    (6, 3, 9600): "Windows 8.1",
    (10, 0, 10240): "Windows 10 1507",
    (10, 0, 10586): "Windows 10 1511",
    (10, 0, 14393): "Windows 10 1607",
    (10, 0, 15063): "Windows 10 1703",
    (10, 0, 16299): "Windows 10 1709",
    (10, 0, 17134): "Windows 10 1803",
    (10, 0, 17763): "Windows 10 1809",
    (10, 0, 18362): "Windows 10 1903",
    (10, 0, 18363): "Windows 10 1909",
    (10, 0, 19041): "Windows 10 2004",
    (10, 0, 19042): "Windows 10 20H2",
    (10, 0, 19043): "Windows 10 21H1",
    (10, 0, 19044): "Windows 10 21H2",
    (10, 0, 19045): "Windows 10 22H2",
    (10, 0, 22000): "Windows 11 21H2",
    (10, 0, 22621): "Windows 11 22H2",
    (10, 0, 22631): "Windows 11 23H2",
    (10, 0, 26100): "Windows 11 24H2",
    (10, 0, 26200): "Windows 11 25H2",
}
NEWEST_GA = max(BUILDS)
ARM64_FLOOR = (10, 0, 16299)  # first build that runs arm64 desktop apps

_IMAGE_FILE_MACHINE = {0x014C: "x86", 0x8664: "x64", 0xAA64: "arm64"}


def parse_build(text: str) -> tuple[int, int, int]:
    parts = (text or "").split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"'{text}' is not a MAJOR.MINOR.BUILD Windows version")
    return int(parts[0]), int(parts[1]), int(parts[2])


def fmt(build: tuple[int, ...]) -> str:
    return ".".join(str(p) for p in build)


def describe(build: tuple[int, int, int]) -> str:
    if build in BUILDS:
        return BUILDS[build]
    older = [b for b in BUILDS if b <= build]
    return f"after {BUILDS[max(older)]}" if older else "older than Windows 7 SP1"


def current() -> tuple[int, int, int] | None:
    if sys.platform != "win32":
        return None
    ver = sys.getwindowsversion()
    return ver.major, ver.minor, ver.build


def ui_language() -> str:
    """Two-letter display language of this PC ("vi", "en", ...); TXA_UI_LANG overrides it."""
    forced = os.environ.get("TXA_UI_LANG", "").strip().lower()
    if forced:
        return forced.split("-")[0]
    if sys.platform == "win32":
        try:
            import ctypes
            import locale

            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            name = locale.windows_locale.get(langid, "")
            if name:
                return name.split("_")[0].lower()
        except (AttributeError, OSError):
            pass
    return "en"


def native_arch() -> str:
    """Real CPU architecture, even when this process runs under emulation."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            process_machine = wintypes.USHORT()
            native_machine = wintypes.USHORT()
            kernel32 = ctypes.windll.kernel32
            if kernel32.IsWow64Process2(
                kernel32.GetCurrentProcess(), ctypes.byref(process_machine), ctypes.byref(native_machine)
            ):
                return _IMAGE_FILE_MACHINE.get(native_machine.value, "x64")
        except (AttributeError, OSError):
            pass
        raw = os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE", "AMD64")
        return {"AMD64": "x64", "ARM64": "arm64", "X86": "x86"}.get(raw.upper(), "x64")
    import platform

    machine = platform.machine().lower()
    return "arm64" if machine in ("arm64", "aarch64") else "x86" if machine in ("i386", "i686", "x86") else "x64"


def arch_preference(native: str) -> list[str]:
    """Architectures a machine can run, best first (arm64 emulates x64 and x86)."""
    return {"arm64": ["arm64", "x64", "x86"], "x64": ["x64", "x86"], "x86": ["x86"]}.get(native, ["x64", "x86"])
