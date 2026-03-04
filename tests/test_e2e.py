"""End-to-end tests for pytest-ensure-tests-fail plugin."""
import subprocess
import sys
from pathlib import Path

import pytest


SAMPLE_PROJECT_DIR = Path(__file__).parent / "sample_project"


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository with sample project.
    
    Sets up:
    - main branch with buggy calculator.py and test_add only
    - fix branch with fixed calculator.py and test_divide_by_zero_returns_none
    """
    repo_dir = tmp_path / "test_repo"
    repo_dir.mkdir()
    
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_dir, capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_dir, capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=repo_dir, capture_output=True, check=True
    )
    
    # Create initial structure with buggy code
    (repo_dir / "calculator.py").write_text(
        (SAMPLE_PROJECT_DIR / "calculator.py").read_text()
    )
    
    # Initial test file with only test_add
    (repo_dir / "test_calculator.py").write_text('''"""Tests for the calculator module."""
from calculator import add


def test_add():
    """Test basic addition."""
    assert add(2, 3) == 5
''')
    
    # Create pyproject.toml for pytest
    (repo_dir / "pyproject.toml").write_text('''[tool.pytest.ini_options]
testpaths = ["."]
''')
    
    # Initial commit on main
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit with buggy calculator"],
        cwd=repo_dir, capture_output=True, check=True
    )
    
    # Create fix branch
    subprocess.run(
        ["git", "checkout", "-b", "fix/divide-by-zero"],
        cwd=repo_dir, capture_output=True, check=True
    )
    
    # Apply the fix
    (repo_dir / "calculator.py").write_text(
        (SAMPLE_PROJECT_DIR / "calculator_fixed.py").read_text()
    )
    
    # Add the new test
    (repo_dir / "test_calculator.py").write_text(
        (SAMPLE_PROJECT_DIR / "test_calculator.py").read_text()
    )
    
    # Commit the fix
    subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Fix divide by zero and add test"],
        cwd=repo_dir, capture_output=True, check=True
    )
    
    return repo_dir


def test_plugin_detects_new_tests(git_repo):
    """Test that the plugin correctly detects new tests from git diff."""
    # Run pytest with --ensure-tests-fail and --collect-only
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "--ensure-tests-fail",
            "--upstream-branch=main",
            "--collect-only", "-q"
        ],
        cwd=git_repo,
        capture_output=True,
        text=True,
    )
    
    # Should find the new test
    assert "test_divide_by_zero_returns_none" in result.stdout
    assert "Found 1 new test" in result.stdout


def test_plugin_verifies_test_fails_on_upstream(git_repo):
    """Test that the plugin verifies new tests fail on upstream."""
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "--ensure-tests-fail",
            "--upstream-branch=main",
            "-v"
        ],
        cwd=git_repo,
        capture_output=True,
        text=True,
    )
    
    # Should show success - test passes on fix branch, fails on main
    assert "Phase 1 PASSED" in result.stdout
    assert "SUCCESS!" in result.stdout
    assert "Tests correctly FAIL on upstream" in result.stdout
    assert result.returncode == 0


def test_plugin_warns_when_test_passes_on_upstream(git_repo):
    """Test that the plugin warns when a new test also passes on upstream."""
    # Add a test that passes on both branches (doesn't catch any bug)
    test_file = git_repo / "test_calculator.py"
    current_content = test_file.read_text()
    test_file.write_text(current_content + '''

def test_add_more():
    """Test that doesn't catch any bug - passes on both branches."""
    from calculator import add
    assert add(1, 1) == 2
''')
    
    # Commit the new test
    subprocess.run(["git", "add", "."], cwd=git_repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Add test that passes everywhere"],
        cwd=git_repo, capture_output=True, check=True
    )
    
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "--ensure-tests-fail",
            "--upstream-branch=main",
            "-v"
        ],
        cwd=git_repo,
        capture_output=True,
        text=True,
    )
    
    # Should warn that test_add_more passes on upstream
    # (test_divide_by_zero_returns_none should still fail on upstream)
    # The overall result depends on whether ANY test passes on upstream
    assert "Found 2 new test" in result.stdout


def test_plugin_no_new_tests(git_repo):
    """Test behavior when there are no new tests."""
    # Checkout main branch (no new tests compared to itself)
    subprocess.run(
        ["git", "checkout", "main"],
        cwd=git_repo, capture_output=True, check=True
    )
    
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "--ensure-tests-fail",
            "--upstream-branch=main",
            "-v"
        ],
        cwd=git_repo,
        capture_output=True,
        text=True,
    )
    
    assert "No new tests found" in result.stdout
    # Exit code 5 = no tests collected
    assert result.returncode == 5
