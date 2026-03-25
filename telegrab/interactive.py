"""terminal interaction helpers"""

from __future__ import annotations

import sys


def has_interactive_terminal() -> bool:
    """return True when stdin/stdout are attached to a tty"""
    return sys.stdin.isatty() and sys.stdout.isatty()
