import pytest
from playwright.sync_api import sync_playwright
import os
import re


def _safe_nodeid(nodeid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", nodeid).strip("_")[:180]


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


@pytest.fixture
def browser():
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=True)
    yield browser
    browser.close()
    playwright.stop()


@pytest.fixture
def context(browser, request):
    context = browser.new_context()
    # Always start tracing; save it only if the test fails.
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    yield context
    failed = bool(getattr(getattr(request.node, "rep_call", None), "failed", False))

    if failed:
        os.makedirs("artifacts", exist_ok=True)
        nodeid = _safe_nodeid(getattr(request.node, "nodeid", "unknown"))
        trace_path = os.path.join("artifacts", f"{nodeid}-trace.zip")
        try:
            context.tracing.stop(path=trace_path)
        except Exception:
            try:
                context.tracing.stop()
            except Exception:
                pass
    else:
        try:
            context.tracing.stop()
        except Exception:
            pass
    context.close()


@pytest.fixture
def page(context, request):
    page = context.new_page()
    yield page

    failed = bool(getattr(getattr(request.node, "rep_call", None), "failed", False))
    if failed:
        os.makedirs("artifacts", exist_ok=True)
        nodeid = _safe_nodeid(request.node.nodeid)
        screenshot_path = os.path.join("artifacts", f"{nodeid}-screenshot.png")
        dom_path = os.path.join("artifacts", f"{nodeid}-dom.html")
        url_path = os.path.join("artifacts", f"{nodeid}-url.txt")
        try:
            page.screenshot(path=screenshot_path, full_page=True)
        except Exception:
            pass
        try:
            with open(dom_path, "w", encoding="utf-8") as f:
                f.write(page.content())
        except Exception:
            pass
        try:
            with open(url_path, "w", encoding="utf-8") as f:
                f.write(page.url)
        except Exception:
            pass
    page.close()
