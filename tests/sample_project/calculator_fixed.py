"""Sample calculator module with bug fixed."""
from typing import Optional


def divide(a: float, b: float) -> Optional[float]:
    """Divide a by b.

    Returns None if b is zero instead of raising ZeroDivisionError.
    """
    if b == 0:
        return None
    return a / b


def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b
