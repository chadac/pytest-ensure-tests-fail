"""Example module with a bug."""


def divide(a: int, b: int) -> float:
    """Divide a by b.
    
    BUG: This doesn't handle division by zero!
    """
    return a / b
