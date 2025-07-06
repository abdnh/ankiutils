import os
import sys


def is_testing() -> bool:
    return "pytest" in sys.modules


def is_devmode() -> bool:
    return "ANKIDEV" in os.environ
