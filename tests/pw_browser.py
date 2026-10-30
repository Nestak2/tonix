"""Test-only browser with the same interface as tonix2.sonix.browser.SeleniumBrowser, built on Playwright."""
import os

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")


def available():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return False
    return os.path.isdir(os.environ["PLAYWRIGHT_BROWSERS_PATH"])


class PlaywrightBrowser:
    def __init__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._b = self._pw.chromium.launch()
        self.page = self._b.new_page()

    def get(self, url):
        self.page.goto(url, wait_until="load")

    @property
    def url(self):
        return self.page.url

    def html(self):
        return self.page.content()

    def js(self, script, *args):
        return self.page.evaluate("([src, args]) => (new Function(src)).apply(null, args)", [script, list(args)])

    def quit(self):
        self._b.close()
        self._pw.stop()
