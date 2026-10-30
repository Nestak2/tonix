"""Local web interface. Only listens on 127.0.0.1, so nobody else on the network can reach it."""
import os
import threading

from flask import Flask, abort, jsonify, request, send_from_directory

from . import classify, pipeline
from .config import Settings, saved_ads_token, saved_openalex_key
from .http import Http
from .ids import parse_orcid

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def default_sonix(settings, log):
    from .sonix.browser import SeleniumBrowser
    from .sonix.client import SonixClient
    return SonixClient(SeleniumBrowser(settings.browser, settings.show_browser), log=log)


def create_app(root=ROOT, sonix_factory=None, http_factory=None):
    app = Flask(__name__, static_folder=os.path.join(HERE, "static"), static_url_path="/static")
    state = {"job": pipeline.Job(), "scimago": classify.Scimago(os.path.join(root, "data"))}
    out_root = os.path.join(root, "output")
    cache_dir = os.path.join(root, ".cache")
    sonix_factory = sonix_factory or default_sonix
    http_factory = http_factory or Http

    def job():
        return state["job"]

    def busy():
        return jsonify({"error": "Still working. Wait until the current step finishes."}), 409

    def body():
        return request.get_json(force=True, silent=True) or {}

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/config")
    def config():
        ads_tok, ads_where = saved_ads_token()
        oa_key, oa_where = saved_openalex_key()
        sc = state["scimago"]
        return jsonify({
            "ads_saved": ads_where if ads_tok else None,
            "openalex_saved": oa_where if oa_key else None,
            "scimago": {"loaded": sc.loaded, "file": os.path.basename(sc.path) if sc.path else None,
                        "journals": len(sc.by_title)},
            "types": classify.TYPE_LABELS,
            "pubtypes": pipeline.PUBTYPE_LABELS, "statuses": pipeline.STATUS_LABELS, "refs": pipeline.REF_LABELS,
        })

    @app.get("/api/status")
    def status():
        return jsonify(job().status())

    @app.post("/api/start")
    def start():
        if job().running:
            return busy()
        data = body()
        orcid_id = parse_orcid(data.get("orcid"))
        if not orcid_id:
            return jsonify({"error": "That ORCID iD isn't valid. It looks like 0000-0002-1825-0097."}), 400
        joined = str(data.get("joined_year") or "").strip()
        if joined and not (joined.isdigit() and 1950 <= int(joined) <= 2100):
            return jsonify({"error": "Enter the year you joined as four digits, or leave it empty."}), 400
        email = (data.get("sonix_email") or "").strip()
        if email and not data.get("sonix_password"):
            return jsonify({"error": "Enter your Sonix password too, or leave both Sonix fields empty to only review."}), 400
        ads_tok = (data.get("ads_token") or "").strip() or saved_ads_token()[0]
        oa_key = (data.get("openalex_key") or "").strip() or saved_openalex_key()[0]
        settings = Settings(
            orcid=orcid_id, sonix_email=email, sonix_password=data.get("sonix_password") or "",
            ads_token=ads_tok, openalex_key=oa_key, contact_email=(data.get("contact_email") or "").strip(),
            joined_year=int(joined) if joined else None, refresh=bool(data.get("refresh")),
            browser="chrome" if data.get("browser") == "chrome" else "firefox",
            show_browser=bool(data.get("show_browser")),
        )
        job().close_sonix()
        j = pipeline.Job()
        j.settings = settings
        j.http = http_factory(cache_dir, ttl=0 if settings.refresh else 24 * 3600, contact_email=settings.contact_email)
        j.make_sonix = sonix_factory
        state["job"] = j
        j.log(f"Started for ORCID {orcid_id}. Sources: INSPIRE, OpenAlex"
              + (" (with key)" if oa_key else " (no key, small daily allowance)")
              + (", ADS" if ads_tok else ""))
        if not state["scimago"].loaded:
            j.log("No Scimago list in the data folder: Scopus indexing and SJR values are not filled in automatically")
        pipeline.run_in_thread(j, pipeline.find_papers, j.http, state["scimago"])
        return jsonify({"ok": True, "orcid": orcid_id})

    @app.get("/api/papers")
    def papers():
        j = job()
        return jsonify({"person": j.person.display if j.person else "", "orcid": j.settings.orcid if j.settings else "",
                        "sonix": bool(j.sonix), "sonix_user": j.sonix_user,
                        "staff": [{"id": s["id"], "label": s["label"]} for s in j.staff],
                        "papers": list(j.papers.values()), "stats": dict(j.stats)})

    @app.post("/api/citations")
    def citations_start():
        j = job()
        if j.running:
            return busy()
        if j.phase not in ("papers_ready", "citations_ready", "done"):
            return jsonify({"error": "Find your papers first."}), 400
        pipeline.apply_choices(j, body().get("papers"), None)
        ids = [pid for pid, p in j.papers.items() if p["cite"] and p["searchable"]]
        if not ids:
            return jsonify({"error": "Tick “Find citations” for at least one paper."}), 400
        pipeline.run_in_thread(j, pipeline.find_citations, j.http, state["scimago"], ids)
        return jsonify({"ok": True, "count": len(ids)})

    @app.get("/api/citations")
    def citations_get():
        j = job()
        return jsonify({"blocks": [dict(b, paper=j.papers[pid]) for pid, b in j.citations.items()]})

    @app.post("/api/plan")
    def plan():
        j = job()
        if j.running:
            return busy()
        data = body()
        pipeline.apply_choices(j, data.get("papers"), data.get("citations"))
        return jsonify(dict(pipeline.make_plan(j), sonix=bool(j.sonix)))

    @app.post("/api/save")
    def save():
        j = job()
        if j.running:
            return busy()
        data = body()
        pipeline.apply_choices(j, data.get("papers"), data.get("citations"))
        p = pipeline.make_plan(j)
        if not p["can_save"]:
            return jsonify({"error": "Nothing can be saved yet: " + ("; ".join(p["problems"]) or "nothing is ticked")}), 400
        pipeline.run_in_thread(j, pipeline.save_job)
        return jsonify({"ok": True})

    @app.post("/api/finish")
    def finish():
        j = job()
        if j.running:
            return busy()
        if j.phase not in ("citations_ready", "saved", "saving", "done", "papers_ready"):
            return jsonify({"error": "Find citations first."}), 400
        data = body()
        if data:
            pipeline.apply_choices(j, data.get("papers"), data.get("citations"))
        return jsonify(pipeline.build_summary(j, out_root))

    @app.get("/api/export/<name>")
    def export(name):
        j = job()
        if not j.summary or name not in j.summary["files"]:
            abort(404)
        return send_from_directory(j.summary["folder"], name, as_attachment=True)

    @app.post("/api/quit")
    def quit_app():
        job().close_sonix()
        threading.Timer(0.5, lambda: os._exit(0)).start()
        return jsonify({"ok": True})

    app.state = state
    return app
