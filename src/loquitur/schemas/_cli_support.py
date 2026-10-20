"""Exit-status rule shared by the package's three commands.

Every command exits 64 (``EX_USAGE`` in BSD ``sysexits.h``) when it is used wrongly or
cannot read or write what it was given, as README.md documents. ``argparse`` exits 2 on a
usage error, so its parser is replaced here by one that exits 64 instead; the message and
the usage line are unchanged and go to stderr.
"""

from __future__ import annotations

import argparse
import sys
from typing import NoReturn

USAGE_ERROR = 64


class UsageErrorParser(argparse.ArgumentParser):
    """An ``ArgumentParser`` whose usage errors exit 64 rather than 2.

    Subparsers created through ``add_subparsers`` take the class of their parent, so a
    subcommand's usage error exits 64 too.
    """

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(USAGE_ERROR, f"{self.prog}: error: {message}\n")
