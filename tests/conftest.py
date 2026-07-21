"""Registers the project's pytest hooks and the `page` fixture override as
plugins. Kept to this one line on purpose — all the actual logic lives in
app/playwright/, where it can be imported and unit-tested independently of
pytest's plugin discovery.
"""

import functools
import http.server
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest_plugins = [
    "app.playwright.conftest_hooks",
    "app.playwright.fixtures",
]


@pytest.fixture(scope="session")
def demo_server() -> Iterator[str]:
    """Serves tests/fixtures/ over loopback-only HTTP for the whole session.

    The sample UI tests need *real* HTTP requests (not `file://`) so that a
    fetch to a missing resource produces an actual 404 response Playwright's
    `page.on("response", ...)` can observe — `fetch()` under `file://` fails
    before it ever reaches the network stack, at the browser's URL-scheme
    check, so it never triggers a request/response event at all. Binding to
    127.0.0.1 keeps this fully offline: no external network is involved.
    """
    directory = str(Path(__file__).parent / "fixtures")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
