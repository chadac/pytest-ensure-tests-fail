"""Sample calculator module with a bug."""


def divide(a: float, b: float) -> float:
    """Divide a by b.

    BUG: Doesn't handle division by zero!
    """
    return a / b


def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b
