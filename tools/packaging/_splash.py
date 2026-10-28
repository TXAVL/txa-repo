"""TXA Packaging UI helper: ANSI console initialization, branding banners, and clean exit handling."""
from __future__ import annotations

import os
import sys


def init_console() -> None:
    """Enable VT100 ANSI escape sequences on Windows console and force UTF-8 output."""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # STD_OUTPUT_HANDLE = -11, STD_ERROR_HANDLE = -12
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            for handle_id in (-11, -12):
                h = kernel32.GetStdHandle(handle_id)
                mode = ctypes.c_ulong()
                if kernel32.GetConsoleMode(h, ctypes.byref(mode)):
                    kernel32.SetConsoleMode(h, mode.value | 0x0004)
        except Exception:
            pass

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def print_banner(tool_name: str, subtitle: str) -> None:
    """Print a clean branded header box when invoked interactively without arguments."""
    try:
        from txa import __version__
        from txa.core import config
    except Exception:
        __version__ = "1.2.0"
        config = None

    # Only show banner if stdout is a real terminal and no arguments were passed
    if len(sys.argv) > 1 or not sys.stdout.isatty():
        return

    lang = config.lang() if config else "vi"
    title = f"⚡ {tool_name.upper()}  ·  v{__version__}"
    tagline = "Hệ thống quản lý và phân phối phần mềm Windows" if lang == "vi" else subtitle
    doc_text = "Tài liệu & Kho mã nguồn: https://github.com/TXAVL/txa-repo" if lang == "vi" else "Docs: https://github.com/TXAVL/txa-repo"

    width = max(len(title) + 6, len(tagline) + 6, len(doc_text) + 6, 68)

    c_box = "\033[38;5;39m"  # Cyan
    c_title = "\033[1;38;5;81m"
    c_sub = "\033[38;5;250m"
    c_doc = "\033[38;5;244m"
    c_reset = "\033[0m"

    top = f"{c_box}╭{'─' * (width - 2)}╮{c_reset}"
    mid = f"{c_box}│{c_reset}"
    bot = f"{c_box}╰{'─' * (width - 2)}╯{c_reset}"

    print(top)
    print(f"{mid}  {c_title}{title:<{width - 4}}{c_reset}{mid}")
    print(f"{mid}  {c_sub}{tagline:<{width - 4}}{c_reset}{mid}")
    print(f"{mid}  {c_doc}{doc_text:<{width - 4}}{c_reset}{mid}")
    print(bot)
    print()

