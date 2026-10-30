"""A thin wrapper around Selenium, so the Sonix code only needs: get, url, html, js, quit."""


class BrowserError(Exception):
    pass


class SeleniumBrowser:
    def __init__(self, kind="firefox", visible=False):
        try:
            from selenium import webdriver
            from selenium.common.exceptions import WebDriverException
        except ImportError:
            raise BrowserError("Selenium is not installed. Run: pip install -r requirements.txt") from None
        self._wde = WebDriverException
        try:
            if kind == "chrome":
                opts = webdriver.ChromeOptions()
                if not visible:
                    opts.add_argument("--headless=new")
                opts.add_argument("--window-size=1280,1000")
                self.d = webdriver.Chrome(options=opts)
            else:
                opts = webdriver.FirefoxOptions()
                if not visible:
                    opts.add_argument("-headless")
                self.d = webdriver.Firefox(options=opts)
        except WebDriverException as exc:
            name = "Chrome" if kind == "chrome" else "Firefox"
            first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
            raise BrowserError(f"{name} could not be started ({first}). Is {name} installed?") from None
        self.d.set_page_load_timeout(90)

    def get(self, url):
        try:
            self.d.get(url)
        except self._wde as exc:
            raise BrowserError(f"The page did not load ({type(exc).__name__})") from None

    @property
    def url(self):
        return self.d.current_url

    def html(self):
        return self.d.page_source

    def js(self, script, *args):
        return self.d.execute_script(script, *args)

    def quit(self):
        try:
            self.d.quit()
        except Exception:
            pass
