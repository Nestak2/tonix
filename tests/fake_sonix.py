"""A small imitation of Sonix built from the real saved pages, for testing.

FakeSonixServer serves login, the publication list, the real "new publication"
and "new citation" forms, and stores what is submitted. FakeSonixClient is a
plain Python stand-in for SonixClient used by the pipeline tests.
"""
import itertools
import os
import re
import threading

from flask import Flask, redirect, request, session
from werkzeug.serving import make_server

from tonix2.sonix import parse

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
REAL = "https://sonix.bas.bg"


def _read(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


def _form(page, start_marker):
    i = page.index(start_marker)
    i = page.rindex("<form", 0, i + 1) if not page[i:].startswith("<form") else i
    j = page.index("</form>", i) + 7
    return page[i:j]


FAKE_JS = """
<script>
const __ajxOriginal = document.getElementById('ajx') ? document.getElementById('ajx').innerHTML : '';
function addAuthorBlock() {
  const w = document.getElementById('authorWrapper');
  const first = w.querySelector('.author');
  const copy = first.cloneNode(true);
  copy.querySelectorAll('input').forEach(i => i.value = '');
  copy.querySelectorAll('select').forEach(s => s.selectedIndex = 0);
  w.appendChild(copy);
}
function makePubFormField(a, v) {
  setTimeout(() => { document.getElementById('ajx').innerHTML = __ajxOriginal; }, 250);
}
</script>
"""


class FakeSonixServer:
    def __init__(self, email="me@inrne.bas.bg", password="right"):
        self.email, self.password = email, password
        self.pubs = parse.parse_publications(_read("sonix_publications.html"))
        self.cites = {p["id"]: [] for p in self.pubs}
        self.cites["140912"] = parse.parse_cites(_read("sonix_cites.html"))
        self.added_pubs, self.added_cites, self.updated_cites = [], [], []
        self._ids = itertools.count(900001)
        self.app = self._make_app()
        self.server = make_server("127.0.0.1", 0, self.app, threaded=True)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()

    # ------------------------------------------------------------ pages
    def _page(self, body, message=""):
        header = (f'<div class="login"><form action="{self.base}/bg/7/session/logoff" method="post">'
                  f'<a href="{self.base}/bg/10/session/myProfile" title="Моят профил">Арсенов, Нестор  • '
                  f'<strong>Служител</strong></a><input type="submit" name="sbm" value="Изход"></form></div>')
        return f"<html><head><title>SONIX</title></head><body>{header}{message}<div class='content'>{body}</div></body></html>"

    def _rows(self, rows, kind):
        out = []
        for k, r in enumerate(rows):
            if kind == "pub":
                out.append(f'<tr class="r{k % 2}"><td class="tc"><a href="{self.base}/bg/258/{r["id"]}/staff/publication">e</a></td>'
                           f'<td class="tl">{r["text"]}</td><td class="tc">&nbsp;</td><td class="tc">{r["year"]}</td>'
                           f'<td class="tc"><a href="{self.base}/bg/242/{r["id"]}/241/staff/cites">{len(self.cites.get(r["id"], []))}</a></td><td></td></tr>')
            else:
                out.append(f'<tr class="r{k % 2}"><td class="tc"><a href="{self.base}/bg/264/{r["pub_id"]}/{r["id"]}/241/staff/cite">e</a></td>'
                           f'<td class="tl">{r["text"]}</td><td class="tc">&nbsp;</td><td class="tc">{r["year"]}</td><td></td></tr>')
        return f'<div id="ajx"><table id="tblsort"><thead><tr><th></th></tr></thead><tbody>{"".join(out)}</tbody></table></div>'

    def _make_app(self):
        app = Flask(__name__)
        app.secret_key = "test"
        srv = self
        login_page = ('<html><body><form action="/bg/7/session/logon" method="post">{msg}'
                      '<input name="email"><input name="pass" type="password"><input type="submit" name="sbm" value="Вход">'
                      '</form></body></html>')

        def need_login():
            return not session.get("ok")

        @app.get("/bg")
        def home():
            if need_login():
                return login_page.format(msg="")
            return srv._page("<h2>Моят профил</h2><input name='gender'>")

        @app.post("/bg/7/session/logon")
        def logon():
            if request.form.get("email") == srv.email and request.form.get("pass") == srv.password:
                session["ok"] = True
                return redirect("/bg/10/session/myProfile")
            return login_page.format(msg='<div class="errorMessage">Невалиден опит за вход в системата</div>')

        @app.get("/bg/10/session/myProfile")
        def profile():
            return srv._page("<h2>Моят профил</h2>") if not need_login() else redirect("/bg")

        @app.post("/bg/7/session/logoff")
        def logoff():
            session.clear()
            return redirect("/bg")

        @app.get("/bg/241/staff/publications")
        def publications():
            if need_login():
                return login_page.format(msg="")
            return srv._page(srv._rows(srv.pubs, "pub"))

        new_pub_form = _form(_read("sonix_new_publication.html"), 'name="fEditing"').replace(REAL, "")

        @app.route("/bg/258/new/staff/publication", methods=["GET", "POST"])
        def new_publication():
            if need_login():
                return login_page.format(msg="")
            if request.method == "GET":
                return srv._page(new_pub_form + FAKE_JS)
            f = request.form
            authors = f.getlist("authors[]")
            if not f.get("title") or not all(authors) or f.get("pubstatusID") in (None, ""):
                return srv._page(new_pub_form + FAKE_JS,
                                 '<div class="errorMessage">Формулярът съдържа невалидно попълнени данни</div>')
            new_id = str(next(srv._ids))
            rec = {k: f.get(k) for k in f.keys() if not k.endswith("[]")}
            rec.update(id=new_id, authors=authors, userIDs=f.getlist("userIDs[]"))
            srv.added_pubs.append(rec)
            srv.pubs.insert(0, {"id": new_id, "text": f"{'; '.join(authors)}. {f['title']}. {f.get('description', '')}",
                                "year": int(f.get("year_pub") or 0) or None, "not_in_report": f.get("report") == "N", "cites": 0})
            srv.cites[new_id] = []
            return redirect(f"/bg/258/{new_id}/staff/publication?saved=1")

        @app.get("/bg/258/<pid>/staff/publication")
        def edit_publication(pid):
            msg = '<div class="successMessage">Записът беше извършен успешно</div>' if request.args.get("saved") else ""
            return srv._page(f'<a href="{srv.base}/bg/242/{pid}/241/staff/cites">Цитирания</a>', msg)

        @app.get("/bg/242/<pid>/241/staff/cites")
        def cites(pid):
            if need_login():
                return login_page.format(msg="")
            return srv._page(srv._rows(srv.cites.get(pid, []), "cite"))

        cite_form = _form(_read("sonix_new_cite.html"), 'name="descr"').replace(REAL, "")

        @app.route("/bg/264/<pid>/new/241/staff/cite", methods=["GET", "POST"])
        def new_cite(pid):
            if need_login():
                return login_page.format(msg="")
            form = cite_form.replace("/264/140912/", f"/264/{pid}/")
            if request.method == "GET":
                return srv._page(form)
            f = request.form
            if not f.get("descr") or not re.fullmatch(r"\d{4}", f.get("year") or "") or f.get("citeTypeID") == "0":
                return srv._page(form, '<div class="errorMessage">Формулярът съдържа невалидно попълнени данни</div>')
            cid = str(next(srv._ids))
            rec = {k: f.get(k) for k in f.keys()}
            rec.update(id=cid, pub_id=pid)
            srv.added_cites.append(rec)
            srv.cites.setdefault(pid, []).append({"id": cid, "pub_id": pid, "text": f["descr"], "year": int(f["year"]),
                                                 "not_in_report": False})
            return srv._page(form, '<div class="successMessage">Записът беше извършен успешно</div>')

        @app.route("/bg/264/<pid>/<cid>/241/staff/cite", methods=["GET", "POST"])
        def edit_cite(pid, cid):
            if need_login():
                return login_page.format(msg="")
            entry = next((c for c in srv.cites.get(pid, []) if c["id"] == cid), None)
            if entry is None:
                return "not found", 404
            form = cite_form.replace(f"/264/140912/new/241/staff/cite", f"/264/{pid}/{cid}/241/staff/cite")
            import html as _h
            form = form.replace('<textarea id="descr" name="descr" class="ta"></textarea>',
                                f'<textarea id="descr" name="descr" class="ta">{_h.escape(entry["text"])}</textarea>')
            form = form.replace('name="year" class="txt"', f'name="year" value="{entry["year"]}" class="txt"')
            msg = ""
            if request.method == "POST":
                f = request.form
                if not f.get("descr") or not re.fullmatch(r"\d{4}", f.get("year") or ""):
                    return srv._page(form, '<div class="errorMessage">Формулярът съдържа невалидно попълнени данни</div>')
                entry.update(text=f["descr"], year=int(f["year"]), type=f.get("citeTypeID"), url=f.get("url"))
                srv.updated_cites.append(dict(entry))
                msg = '<div class="successMessage">Редакцията беше извършена успешно</div>'
            return srv._page(form, msg)

        return app


class FakeSonixClient:
    """Stand-in for SonixClient with the same methods, no browser."""
    base = "https://sonix.example"

    def __init__(self, pubs, cites, staff, user="Петрова, Елена", password="right"):
        self.pubs, self.cite_lists, self._staff = pubs, cites, staff
        self.user, self.password = user, password
        self.added_pubs, self.added_cites, self.updated_cites, self.closed = [], [], [], False
        self._ids = itertools.count(500)

    def login(self, email, password):
        from tonix2.sonix.client import SonixError
        if password != self.password:
            raise SonixError("Sonix did not accept the email or password")
        return self.user

    def publications(self):
        return list(self.pubs)

    def staff(self):
        return list(self._staff)

    def cites(self, pid):
        return list(self.cite_lists.get(pid, []))

    def add_publication(self, f):
        new_id = str(next(self._ids))
        self.added_pubs.append(dict(f, id=new_id))
        self.pubs.append({"id": new_id, "text": f["title"], "year": int(f["year_pub"] or 0), "not_in_report": False, "cites": 0})
        return new_id, []

    def add_citation(self, pid, c):
        self.added_cites.append(dict(c, pub_id=pid))

    def update_citation(self, pid, cid, c):
        self.updated_cites.append(dict(c, pub_id=pid, cite_id=cid))

    def close(self):
        self.closed = True
