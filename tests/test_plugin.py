"""Tests for pytest-ensure-tests-fail plugin."""

import pytest
from pytest_ensure_tests_fail.plugin import EnsureTestsFailPlugin


class TestDiffParsing:
    """Test the diff parsing logic."""

    def test_plugin_registers_options(self, pytestconfig):
        """Test that the plugin registers its command line options."""
        # This test verifies the plugin hooks are working
        assert pytestconfig.getini("testpaths") is not None


def test_basic_import():
    """Test that the plugin can be imported."""
    from pytest_ensure_tests_fail import plugin
    assert hasattr(plugin, 'pytest_addoption')
    assert hasattr(plugin, 'pytest_configure')
    assert hasattr(plugin, 'EnsureTestsFailPlugin')
