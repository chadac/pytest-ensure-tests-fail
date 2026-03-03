"""Tests for the example module."""

from pytest_ensure_tests_fail.example import divide


def test_normal_division():
    """Test that normal division works."""
    assert divide(10, 2) == 5.0
    assert divide(9, 3) == 3.0
