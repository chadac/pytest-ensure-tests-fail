"""Tests for the example module."""

from pytest_ensure_tests_fail.example import divide


def test_normal_division():
    """Test that normal division works."""
    assert divide(10, 2) == 5.0
    assert divide(9, 3) == 3.0


def test_divide_by_zero_returns_none():
    """Test that dividing by zero returns None instead of raising."""
    # This test SHOULD fail on main because the bug exists
    result = divide(10, 0)
    assert result is None
