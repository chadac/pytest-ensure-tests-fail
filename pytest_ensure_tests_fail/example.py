"""Example module - now with proper error handling."""

from typing import Optional


def divide(a: int, b: int) -> Optional[float]:
    """Divide a by b.
    
    Returns None if b is zero (instead of raising ZeroDivisionError).
    """
    if b == 0:
        return None
    return a / b
