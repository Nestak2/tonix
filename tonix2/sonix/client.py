"""Drive the Sonix web site the way a person would: open pages, fill fields, press "Запис"."""
import re
import time

from . import match, parse

BASE = "https://sonix.bas.bg"
PUBLICATIONS = "/bg/241/staff/publications"
NEW_PUBLICATION = "/bg/258/new/staff/publication"
CITES = "/bg/242/{pid}/241/staff/cites"
NEW_CITE = "/bg/264/{pid}/new/241/staff/cite"
EDIT_CITE = "/bg/264/{pid}/{cid}/241/staff/cite"

# Fill one field (input, textarea or select) by name; fire the events Sonix listens to.
_SET = """
const [name, idx, val] = arguments;
const els = document.getElementsByName(name);
const el = els[idx];
if (!el) return 'missing';
if (el.tagName === 'SELECT' && ![...el.options].some(o => o.value === String(val))) return 'nooption';
el.value = String(val);
el.dispatchEvent(new Event('input', {bubbles: true}));
el.dispatchEvent(new Event('change', {bubbles: true}));
return 'ok';
"""
_RADIO = """
const el = document.querySelector('input[name="' + arguments[0] + '"][value="' + arguments[1] + '"]');
if (!el) return false; el.checked = true; return true;
"""
_SUBMIT = """
window.__tonixOld = true;
const b = document.querySelector('input.btn[type="submit"]');
if (!b) return false; b.click(); return true;
"""
_LOGIN = """
const [email, pass] = arguments;
const p = document.getElementsByName('pass')[0];
const e = document.getElementsByName('email')[0];
if (!p || !e) return false;
e.value = email; p.value = pass;
window.__tonixOld = true;
const f = p.form;
const s = f && f.querySelector('[name="sbm"]');
if (s) s.click(); else f.submit();
return true;
"""
_NEW_PAGE = "return !window.__tonixOld && document.readyState === 'complete';"
_MESSAGES = """
const ok = document.querySelector('.successMessage');
const errs = [...document.querySelectorAll('.errorMessage, .error, [class*="rror"]')]
  .map(e => e.innerText.trim()).filter(Boolean);
return {ok: ok ? ok.innerText.trim() : '', errors: errs.slice(0, 6)};
"""


class SonixError(Exception):
    pass


class SonixClient:
    def __init__(self, browser, base=BASE, pause=1.5, log=None):
        self.b = browser
        self.base = base.rstrip("/")
        self.pause = pause
        self.log = log or (lambda msg, level="info": None)
        self._creds = None
        self.user = None

    # ------------------------------------------------------------ helpers
    def _wait(self, js, timeout=30, interval=0.25):
        end = time.time() + timeout
        while time.time() < end:
            try:
                if self.b.js(js):
                    return True
            except Exception:       # page is navigating
                pass
            time.sleep(interval)
        return False

    def _open(self, path, ready_js):
        """Open a page, signing in again if the session has expired."""
        for attempt in range(2):
            self.b.get(self.base + path)
            self._wait("return document.readyState === 'complete';", 30)
            page = self.b.html()
            if parse.is_login_page(page) and self._creds and attempt == 0:
                self.log("Sonix session expired, signing in again")
                self.login(*self._creds)
                continue
            if not self._wait(ready_js, 20):
                raise SonixError(f"Sonix page {path} did not show what was expected")
            return self.b.html()
        raise SonixError("Sonix keeps asking to sign in")

    def _set(self, name, value, idx=0, required=False):
        if value is None:
            return True
        res = self.b.js(_SET, name, idx, value)
        if res != "ok":
            if required:
                raise SonixError(f"Sonix form field '{name}' could not be filled ({res})")
            return False
        return True

    def _submit(self):
        if not self.b.js(_SUBMIT):
            raise SonixError("The 'Запис' button was not found")
        if not self._wait(_NEW_PAGE, 60):
            raise SonixError("Sonix did not answer after pressing 'Запис' (server busy?)")
        return self.b.js(_MESSAGES) or {}

    # ------------------------------------------------------------ session
    def login(self, email, password):
        self._creds = (email, password)
        self.b.get(self.base + "/bg")
        self._wait("return document.readyState === 'complete';", 30)
        if parse.is_logged_in(self.b.html()):
            self.user = parse.parse_current_user(self.b.html())
            return self.user
        if not self._wait("return !!document.getElementsByName('pass')[0];", 20):
            raise SonixError("The Sonix sign-in page did not load")
        self.b.js(_LOGIN, email, password)
        self._wait(_NEW_PAGE, 45)
        page = self.b.html()
        if not parse.is_logged_in(page):
            raise SonixError("Sonix did not accept the email or password")
        self.user = parse.parse_current_user(page)
        return self.user

    def logout(self):
        try:
            self.b.js("const f=document.querySelector('form[action*=\"session/logoff\"]'); if(f) f.submit();")
            time.sleep(1)
        except Exception:
            pass

    def close(self):
        self.logout()
        self.b.quit()

    # ------------------------------------------------------------ reading
    def publications(self):
        page = self._open(PUBLICATIONS, "return !!document.getElementById('tblsort');")
        if self.user is None:
            self.user = parse.parse_current_user(page)
        return parse.parse_publications(page)

    def cites(self, pub_id):
        page = self._open(CITES.format(pid=pub_id), "return !!document.getElementById('tblsort');")
        return parse.parse_cites(page)

    def staff(self):
        page = self._open(NEW_PUBLICATION, "return !!document.getElementsByName('userIDs[]')[0];")
        return parse.parse_staff(page)

    # ------------------------------------------------------------ writing
    def add_publication(self, f):
        """f: dict with Sonix field names plus 'authors': [(name, staff_id)], 'report': 'Y'/'N'.
        Returns (new publication id or None, list of fields that the form did not have)."""
        self._open(NEW_PUBLICATION, "return !!document.getElementsByName('title')[0];")
        missing = []
        current = self.b.js("const s=document.getElementsByName('pubtypeID')[0]; return s ? s.value : null;")
        if f.get("pubtypeID") and str(current) != str(f["pubtypeID"]):
            self.b.js("const t=document.getElementsByName('title')[0]; if (t) t.dataset.tonixOld='1';")
            self._set("pubtypeID", f["pubtypeID"], required=True)
            # the form reloads its lower part for the new type
            self._wait("const t=document.getElementsByName('title')[0]; return t && !t.dataset.tonixOld;", 10)
            time.sleep(0.3)

        authors = f.get("authors") or []
        for _ in range(len(authors) - 1):
            self.b.js("if (typeof addAuthorBlock === 'function') addAuthorBlock();")
        if not self._wait(f"return document.getElementsByName('authors[]').length >= {max(1, len(authors))};", 10):
            raise SonixError("Sonix did not add enough author fields")
        for i, (name, sid) in enumerate(authors):
            self._set("authors[]", name[:30], i, required=True)
            self._set("userIDs[]", sid or "0", i, required=True)

        order = ["corBAS", "authorsNum", "fauthor", "year_accept", "year_pub", "title", "description", "publisher",
                 "volume", "number", "issn", "isbn", "doi", "page_bgn", "page_end", "pubstatusID", "refID",
                 "isiif", "sjr", "url", "note"]
        for name in order:
            val = f.get(name)
            if val in (None, ""):
                continue
            if not self._set(name, val, required=name in ("title", "pubstatusID")):
                missing.append(name)
        self.b.js(_RADIO, "report", f.get("report", "Y"))
        msg = self._submit()
        if not msg.get("ok"):
            raise SonixError("Sonix refused the publication: " + ("; ".join(msg.get("errors") or []) or "no message"))
        m = re.search(r"/258/(\d+)/staff/publication", self.b.url or "") or \
            re.search(r"/242/(\d+)/\d+/staff/cites", self.b.html() or "")
        time.sleep(self.pause)
        return (m.group(1) if m else None), missing

    def add_citation(self, pub_id, c):
        """c: dict with descr, citeTypeID, year, url, note, report."""
        self._open(NEW_CITE.format(pid=pub_id), "return !!document.getElementsByName('descr')[0];")
        self._set("descr", c["descr"], required=True)
        self._set("citeTypeID", c["citeTypeID"], required=True)
        self._set("year", c["year"], required=True)
        if c.get("url"):
            self._set("url", c["url"][:250])
        if c.get("note"):
            self._set("note", c["note"])
        self.b.js(_RADIO, "report", c.get("report", "Y"))
        msg = self._submit()
        if not msg.get("ok"):
            raise SonixError("Sonix refused the citation: " + ("; ".join(msg.get("errors") or []) or "no message"))
        time.sleep(self.pause)

    def update_citation(self, pub_id, cite_id, c):
        """Overwrite an existing citation (e.g. its arXiv version with the journal version).
        c: descr, citeTypeID, year, url, and old_text: what Sonix showed for it, checked before changing."""
        self._open(EDIT_CITE.format(pid=pub_id, cid=cite_id), "return !!document.getElementsByName('descr')[0];")
        current = self.b.js("const d=document.getElementsByName('descr')[0]; return d ? d.value : '';") or ""
        if c.get("old_text") and not match.same_text(current, c["old_text"]):
            raise SonixError("The Sonix edit page shows a different citation, so it was left unchanged")
        self._set("descr", c["descr"], required=True)
        self._set("citeTypeID", c["citeTypeID"], required=True)
        self._set("year", c["year"], required=True)
        self._set("url", (c.get("url") or "")[:250])
        msg = self._submit()
        if not msg.get("ok"):
            raise SonixError("Sonix refused the change: " + ("; ".join(msg.get("errors") or []) or "no message"))
        time.sleep(self.pause)
