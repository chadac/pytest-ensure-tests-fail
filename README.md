# pytest-ensure-tests-fail

A pytest plugin that ensures your new tests actually catch bugs by
verifying they fail on the upstream branch.

## Why?

When you write news tests, generally those tests should **pass** on
your branch but **fail** on the upstream target. Otherwise, it's
likely not capturing what you think it is!

This plugin is fairly simple. It detects your upstream, then
selectively runs the tests you've added or modified on the
upstream. It fails if any of those tests succeed.

## Installation

```bash
pip install pytest-ensure-tests-fail
```

Or with uv:

```bash
uv add pytest-ensure-tests-fail
```

## Usage

```bash
# Run with automatic upstream detection (main/master)
pytest --ensure-tests-fail

# Specify the upstream branch explicitly
pytest --ensure-tests-fail --upstream-branch=origin/main
```

## How it works

1. Diffs your current branch against the upstream branch
2. Identifies newly added test functions/methods from the diff
3. Runs only those new tests on your current branch
4. If they pass, checks out the upstream branch and runs them again
5. Verifies the tests fail on upstream (proving they catch the bug)

## Example output

```
============================================================
pytest-ensure-tests-fail
============================================================
Current branch: fix/login-bug
Upstream branch: origin/main

Found 2 new test(s):
  - tests/test_auth.py::test_login_with_special_chars
  - tests/test_auth.py::TestLogin::test_empty_password
============================================================

...

============================================================
Phase 1 PASSED: All new tests pass on current branch
============================================================

Phase 2: Checking if tests fail on upstream...
(This verifies the tests actually catch the bug)

============================================================
SUCCESS! Tests correctly fail on upstream branch.
This confirms your tests catch the bug that was fixed.
============================================================
```

## License

MIT
