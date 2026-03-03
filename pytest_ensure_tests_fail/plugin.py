"""pytest plugin to ensure new tests actually fix issues.

When running with --ensure-tests-fail, this plugin:
1. Diffs the current branch against the upstream branch
2. Identifies newly added test functions/methods
3. Runs only those new tests
4. Verifies they pass on the current branch
5. Creates a worktree of upstream and verifies tests fail there
"""

import shutil
import subprocess
import re
import tempfile
import sys
from pathlib import Path
from typing import Set, Optional


# Global state for the plugin instance (created when flag is active)
_plugin_instance: Optional["EnsureTestsFailPlugin"] = None


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
    global _plugin_instance
    if config.getoption("--ensure-tests-fail"):
        _plugin_instance = EnsureTestsFailPlugin(config)


def pytest_sessionstart(session):
    """Called at the start of the test session."""
    if _plugin_instance:
        _plugin_instance.pytest_sessionstart(session)


def pytest_collection_modifyitems(session, config, items):
    """Filter to only run new tests."""
    if _plugin_instance:
        _plugin_instance.pytest_collection_modifyitems(session, config, items)


def pytest_sessionfinish(session, exitstatus):
    """Called at the end of the test session."""
    if _plugin_instance:
        _plugin_instance.pytest_sessionfinish(session, exitstatus)


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
        user_upstream = self.config.getoption("--upstream-branch")
        if user_upstream:
            return user_upstream

        for branch in ["main", "master"]:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", f"origin/{branch}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return f"origin/{branch}"

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

    def _parse_new_tests_from_diff(self) -> Set[str]:
        """Parse the git diff to find newly added test functions."""
        new_tests = set()

        assert self.upstream_branch is not None
        result = subprocess.run(
            ["git", "diff", "-U0", self.upstream_branch, "--", "*.py"],
            capture_output=True,
            text=True,
            check=True,
        )

        current_file: Optional[str] = None
        current_class: Optional[str] = None

        file_pattern = re.compile(r"^\+\+\+ b/(.+)$")
        test_func_pattern = re.compile(r"^\+\s*(async\s+)?def\s+(test_\w+)\s*\(")
        class_pattern = re.compile(r"^[\s+]?class\s+(\w+)")
        hunk_pattern = re.compile(
            r"^@@.*@@\s*(?:class\s+(\w+)|(?:async\s+)?def\s+(\w+))?"
        )

        for line in result.stdout.split("\n"):
            file_match = file_pattern.match(line)
            if file_match:
                current_file = file_match.group(1)
                current_class = None
                continue

            if current_file and not (
                "test_" in current_file or current_file.endswith("_test.py")
            ):
                continue

            hunk_match = hunk_pattern.match(line)
            if hunk_match:
                if hunk_match.group(1):
                    current_class = hunk_match.group(1)
                elif hunk_match.group(2) and not hunk_match.group(2).startswith(
                    "test_"
                ):
                    current_class = None
                continue

            class_match = class_pattern.match(line)
            if class_match and line.startswith("+"):
                current_class = class_match.group(1)
                continue

            test_match = test_func_pattern.match(line)
            if test_match and current_file:
                test_name = test_match.group(2)
                if current_class:
                    node_id = f"{current_file}::{current_class}::{test_name}"
                else:
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
            config.hook.pytest_deselected(items=items[:])
            items[:] = []
            return

        selected = []
        deselected = []

        for item in items:
            node_id = item.nodeid
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

        if exitstatus == 0:
            print(f"\n{'='*60}")
            print("Phase 1 PASSED: All new tests pass on current branch")
            print(f"{'='*60}")
            print("\nPhase 2: Checking if tests fail on upstream...")
            print("(This verifies the tests actually catch the bug)")

            self._verify_tests_fail_on_upstream(session)
        else:
            print(f"\n{'='*60}")
            print("FAILED: New tests don't pass on current branch!")
            print("Fix your tests before verifying they catch bugs.")
            print(f"{'='*60}\n")

    def _verify_tests_fail_on_upstream(self, session):
        """Verify that new tests fail on the upstream branch.

        Uses git worktree to create a clean checkout of upstream,
        preserving the current working directory state completely.
        """
        assert self.upstream_branch is not None

        # Create a temporary directory for the worktree
        worktree_dir = tempfile.mkdtemp(prefix="pytest-ensure-tests-fail-")

        try:
            # Create a worktree at upstream branch
            # This is a clean checkout that doesn't affect current working state
            print(f"\nCreating worktree at {worktree_dir}...")
            result = subprocess.run(
                [
                    "git",
                    "worktree",
                    "add",
                    "--detach",
                    worktree_dir,
                    self.upstream_branch,
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                print(f"Failed to create worktree: {result.stderr}")
                return

            # Copy test files from current branch to the worktree
            # This allows us to run the new tests against the old code
            print("Copying new test files to upstream worktree...")
            for test_node_id in self.new_tests:
                # Extract file path from node_id (e.g., "tests/test_foo.py::test_bar")
                test_file = test_node_id.split("::")[0]
                src_path = self.repo_root / test_file
                dst_path = Path(worktree_dir) / test_file

                if src_path.exists():
                    dst_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_path, dst_path)

            # Run pytest in the worktree directory
            # Convert node_ids to be relative to the worktree
            test_args = [node_id.split("::")[0] + "::" + "::".join(node_id.split("::")[1:])
                        for node_id in self.new_tests]

            print(f"Running tests in upstream worktree...")
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-v", "--tb=short"] + test_args,
                capture_output=True,
                text=True,
                cwd=worktree_dir,
            )

            if result.returncode == 0:
                print(f"\n{'='*60}")
                print("WARNING: Tests PASS on upstream branch!")
                print("This means your tests don't actually catch the bug.")
                print("The tests should fail on upstream and pass on your branch.")
                print(f"{'='*60}")
                print("\nUpstream test output:")
                print(result.stdout)
                if result.stderr:
                    print(result.stderr)
                session.exitstatus = 1
            elif result.returncode == 1:
                print(f"\n{'='*60}")
                print("SUCCESS! Tests correctly FAIL on upstream branch.")
                print("This confirms your tests catch the bug that was fixed.")
                print(f"{'='*60}")
                print("\nUpstream test output (showing failures):")
                print(result.stdout)
                if result.stderr:
                    print(result.stderr)
            elif result.returncode == 4:
                print(f"\n{'='*60}")
                print("SUCCESS! Tests don't exist on upstream branch.")
                print("(New test files are not present in upstream)")
                print("This is valid - your tests are brand new.")
                print(f"{'='*60}\n")
            elif result.returncode == 5:
                print(f"\n{'='*60}")
                print("Note: No tests were collected on upstream.")
                print("(Test files may have import errors on upstream)")
                print("\nOutput:")
                print(result.stdout)
                if result.stderr:
                    print(result.stderr)
                print(f"{'='*60}\n")
            else:
                print(f"\n{'='*60}")
                print(f"Note: pytest exited with code {result.returncode} on upstream")
                print("This may indicate an issue running tests on upstream.")
                print("\nOutput:")
                print(result.stdout)
                if result.stderr:
                    print(result.stderr)
                print(f"{'='*60}\n")

        finally:
            # Clean up the worktree
            subprocess.run(
                ["git", "worktree", "remove", "--force", worktree_dir],
                capture_output=True,
                text=True,
            )
            # Also try to remove the temp directory if it still exists
            if Path(worktree_dir).exists():
                shutil.rmtree(worktree_dir, ignore_errors=True)
