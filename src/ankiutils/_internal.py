import sys


def is_testing() -> bool:
    return "pytest" in sys.modules
