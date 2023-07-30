from .constants import BRD_CONST_DATA
import time
import sys
from pathlib import Path, PurePath


class bcolors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


from inspect import getouterframes


def stack():
    """Return a list of records for the stack above the caller's frame."""
    (frame, source, lineno, func, lines, index) = getouterframes(sys._getframe(1), 1)[
        -1
    ]
    return "bradley." + Path(source).stem


class Logging:
    def debug(self, message, multi_line=False):

        if BRD_CONST_DATA.__DYN__.Debug:

            tm = (
                time.strftime("%d-%m-%Y %H:%M:%S")
                + ":"
                + str(round(time.time() * 1000))
            )
            msg = (
                message
                if not multi_line
                else "↓ ------------ ↓\n" + message + "\n↑ ------------ ↑"
            )
            print(
                bcolors.OKGREEN
                + f"[{tm}]"
                + bcolors.ENDC
                + " | "
                + bcolors.WARNING
                + "DEBUG"
                + bcolors.ENDC
                + " | "
                + bcolors.OKBLUE
                + str(stack())
                + bcolors.ENDC
                + " | "
                + msg
            )


log = Logging()
