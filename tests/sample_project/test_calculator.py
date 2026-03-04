"""Tests for the calculator module."""
from calculator import divide, add


def test_add():
    """Test basic addition."""
    assert add(2, 3) == 5


def test_divide_by_zero_returns_none():
    """Test that dividing by zero returns None.
    
    This test should FAIL on the buggy version and PASS on the fixed version.
    """
    result = divide(10, 0)
    assert result is None
