"""pytest plugin to ensure new tests actually fix issues.

When running with --ensure-tests-fail, this plugin:
1. Diffs the current branch against the upstream branch
2. Identifies newly added test functions/methods
3. Runs only those new tests
4. Verifies they pass on the current branch
5. Checks out upstream and verifies they fail there
"""

import subprocess
import re
import pytest
from pathlib import Path
from typing import List, Set, Tuple, Optional


def pytest_addoption(parser):
    """Add command line options for the plugin."""
    group = parser.getgroup("ensure-tests-fail")
    group.addoption(
        "--ensure-tests-fail",
        action="store_true",
        default=False,
        help="Run only new tests and verify they fail on upstream branch",
    )
    group.addoption(
        "--upstream-branch",
        action="store",
        default=None,
        help="Upstream branch to compare against (default: auto-detect main/master)",
    )


def pytest_configure(config):
    """Configure the plugin."""
    if config.getoption("--ensure-tests-fail"):
        config.pluginmanager.register(EnsureTestsFailPlugin(config), "ensure_tests_fail")


class EnsureTestsFailPlugin:
    """Plugin that ensures new tests actually catch bugs."""

    def __init__(self, config):
        self.config = config
        self.new_tests: Set[str] = set()
        self.upstream_branch: Optional[str] = None
        self.current_branch: Optional[str] = None
        self.repo_root: Path = self._get_repo_root()

    def _get_repo_root(self) -> Path:
        """Get the root of the git repository."""
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())

    def _get_current_branch(self) -> str:
        """Get the current git branch name."""
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def _detect_upstream_branch(self) -> str:
        """Auto-detect the upstream branch (main or master)."""
        # Check if user specified upstream
        user_upstream = self.config.getoption("--upstream-branch")
        if user_upstream:
            return user_upstream

        # Try to detect from remote
        for branch in ["main", "master"]:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", f"origin/{branch}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return f"origin/{branch}"

        # Fall back to local branches
        for branch in ["main", "master"]:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", branch],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return branch

        raise ValueError(
            "Could not auto-detect upstream branch. "
            "Please specify with --upstream-branch"
        )

    def _get_diff_new_test_files(self) -> List[Path]:
        """Get list of new or modified test files from the diff."""
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=AM", self.upstream_branch],
            capture_output=True,
            text=True,
            check=True,
        )
        files = []
        for line in result.stdout.strip().split("\n"):
            if line and (line.startswith("test_") or "/test_" in line or line.endswith("_test.py")):
                path = self.repo_root / line
                if path.exists():
                    files.append(path)
        return files

    def _parse_new_tests_from_diff(self) -> Set[str]:
        """Parse the git diff to find newly added test functions."""
        new_tests = set()

        # Get the diff with function context
        result = subprocess.run(
            ["git", "diff", "-U0", self.upstream_branch, "--", "*.py"],
            capture_output=True,
            text=True,
            check=True,
        )

        current_file = None
        current_class = None

        # Patterns to match
        file_pattern = re.compile(r"^\+\+\+ b/(.+)$")
        # Match added lines that define test functions or methods
        test_func_pattern = re.compile(r"^\+\s*(async\s+)?def\s+(test_\w+)\s*\(")
        # Match class definitions in context or added
        class_pattern = re.compile(r"^[\s+]?class\s+(\w+)")
        # Hunk header with function context
        hunk_pattern = re.compile(r"^@@.*@@\s*(?:class\s+(\w+)|(?:async\s+)?def\s+(\w+))?")

        for line in result.stdout.split("\n"):
            # Track current file
            file_match = file_pattern.match(line)
            if file_match:
                current_file = file_match.group(1)
                current_class = None
                continue

            # Skip non-test files
            if current_file and not (
                "test_" in current_file or current_file.endswith("_test.py")
            ):
                continue

            # Check hunk header for class context
            hunk_match = hunk_pattern.match(line)
            if hunk_match:
                if hunk_match.group(1):  # Class in context
                    current_class = hunk_match.group(1)
                elif hunk_match.group(2) and not hunk_match.group(2).startswith("test_"):
                    # Regular function context, not in a class
                    current_class = None
                continue

            # Check for class definition in diff
            class_match = class_pattern.match(line)
            if class_match and line.startswith("+"):
                current_class = class_match.group(1)
                continue

            # Check for new test function
            test_match = test_func_pattern.match(line)
            if test_match and current_file:
                test_name = test_match.group(2)
                if current_class:
                    # Method in a class
                    node_id = f"{current_file}::{current_class}::{test_name}"
                else:
                    # Top-level function
                    node_id = f"{current_file}::{test_name}"
                new_tests.add(node_id)

        return new_tests

    def pytest_sessionstart(self, session):
        """Called at the start of the test session."""
        self.current_branch = self._get_current_branch()
        self.upstream_branch = self._detect_upstream_branch()

        print(f"\n{'='*60}")
        print("pytest-ensure-tests-fail")
        print(f"{'='*60}")
        print(f"Current branch: {self.current_branch}")
        print(f"Upstream branch: {self.upstream_branch}")

        # Find new tests
        self.new_tests = self._parse_new_tests_from_diff()

        if not self.new_tests:
            print("\nNo new tests found in diff!")
            print("This plugin only runs newly added test functions.")
            print(f"{'='*60}\n")
        else:
            print(f"\nFound {len(self.new_tests)} new test(s):")
            for test in sorted(self.new_tests):
                print(f"  - {test}")
            print(f"{'='*60}\n")

    def pytest_collection_modifyitems(self, session, config, items):
        """Filter to only run new tests."""
        if not self.new_tests:
            # Deselect all tests if no new tests found
            config.hook.pytest_deselected(items=items[:])
            items[:] = []
            return

        selected = []
        deselected = []

        for item in items:
            # Build the node ID without parameters for matching
            # item.nodeid might be like "tests/test_foo.py::TestClass::test_method[param]"
            # We want to match against "tests/test_foo.py::TestClass::test_method"
            node_id = item.nodeid
            # Remove any parametrize suffixes for matching
            base_node_id = re.sub(r"\[.*\]$", "", node_id)

            if base_node_id in self.new_tests or node_id in self.new_tests:
                selected.append(item)
            else:
                deselected.append(item)

        if deselected:
            config.hook.pytest_deselected(items=deselected)

        items[:] = selected

    def pytest_sessionfinish(self, session, exitstatus):
        """Called at the end of the test session."""
        if not self.new_tests:
            return

        # Check if all tests passed
        if exitstatus == 0:
            print(f"\n{'='*60}")
            print("Phase 1 PASSED: All new tests pass on current branch")
            print(f"{'='*60}")
            print("\nPhase 2: Checking if tests fail on upstream...")
            print("(This verifies the tests actually catch the bug)")

            # Now we need to verify tests fail on upstream
            # We'll do this by running pytest again on the upstream branch
            self._verify_tests_fail_on_upstream(session)
        else:
            print(f"\n{'='*60}")
            print("FAILED: New tests don't pass on current branch!")
            print("Fix your tests before verifying they catch bugs.")
            print(f"{'='*60}\n")

    def _verify_tests_fail_on_upstream(self, session):
        """Verify that new tests fail on the upstream branch."""
        # Stash any uncommitted changes
        stash_result = subprocess.run(
            ["git", "stash", "push", "-m", "pytest-ensure-tests-fail-temp"],
            capture_output=True,
            text=True,
        )
        has_stash = "No local changes" not in stash_result.stdout

        try:
            # Checkout upstream branch
            subprocess.run(
                ["git", "checkout", self.upstream_branch],
                capture_output=True,
                text=True,
                check=True,
            )

            # Run pytest on the new tests
            test_args = list(self.new_tests)
            result = subprocess.run(
                ["pytest", "-x"] + test_args,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                print(f"\n{'='*60}")
                print("SUCCESS! Tests correctly fail on upstream branch.")
                print("This confirms your tests catch the bug that was fixed.")
                print(f"{'='*60}\n")
            else:
                print(f"\n{'='*60}")
                print("WARNING: Tests PASS on upstream branch!")
                print("This means your tests don't actually catch the bug.")
                print("The tests should fail on upstream and pass on your branch.")
                print(f"{'='*60}\n")
                # This is a failure condition
                session.exitstatus = 1

        finally:
            # Return to original branch
            subprocess.run(
                ["git", "checkout", self.current_branch],
                capture_output=True,
                text=True,
            )

            # Restore stashed changes
            if has_stash:
                subprocess.run(
                    ["git", "stash", "pop"],
                    capture_output=True,
                    text=True,
                )
