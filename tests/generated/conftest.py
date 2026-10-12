"""Fixtures and guardrails for agent-written tests.

Written by humans. write_test only accepts test_*.py, so the agent can't overwrite this file.
"""

from urllib.parse import urlparse

import pytest
from playwright.sync_api import expect

from agent.tools import ALLOWED_HOSTS, load_test_users

# Fail fast: a missing element should cost seconds, not the 30s default.
TIMEOUT_MS = 5_000
expect.set_options(timeout=TIMEOUT_MS)


@pytest.fixture
def patient() -> dict:
    """The default synthetic test user (Jordan Rivera, TEST-000123)."""
    return load_test_users()[0]


@pytest.fixture
def patients() -> list[dict]:
    return load_test_users()


@pytest.fixture(autouse=True)
def localhost_only(context):
    """Enforce the URL allowlist inside the browser: any non-localhost request is aborted."""
    def guard(route):
        if urlparse(route.request.url).hostname in ALLOWED_HOSTS:
            route.continue_()
        else:
            route.abort("blockedbyclient")

    context.route("**/*", guard)
    context.set_default_timeout(TIMEOUT_MS)
    yield
