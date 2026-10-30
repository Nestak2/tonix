import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fake_sonix  # noqa: E402
import pw_browser  # noqa: E402
from fake_api import ORCID_ID, FakeHttp  # noqa: E402
from tonix2 import fmt, pipeline  # noqa: E402
from tonix2.config import Settings  # noqa: E402
from tonix2.model import Merged  # noqa: E402
from tonix2.sonix import match, parse  # noqa: E402
from tonix2.sonix.client import SonixClient, SonixError  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


needs_fixtures = pytest.mark.skipif(
    not os.path.exists(os.path.join(FIX, "sonix_publications.html")),
    reason="saved Sonix pages are not in tests/fixtures (they hold personal data and are not published)")


def read(name):
    return open(os.path.join(FIX, name), encoding="utf-8").read()


# ------------------------------------------------------------------ parsing the real pages
@needs_fixtures
def test_parse_publication_list():
    pubs = parse.parse_publications(read("sonix_publications.html"))
    assert len(pubs) == 5
    first = pubs[0]
    assert first["id"] == "164271" and first["year"] == 2026 and first["cites"] == 0
    assert "Tracing the high-z cosmic web" in first["text"] and not first["not_in_report"]
    assert [p["cites"] for p in pubs] == [0, 0, 0, 2, 6]
    assert parse.parse_current_user(read("sonix_publications.html")) == "Арсенов, Нестор"
    assert parse.is_logged_in(read("sonix_publications.html"))


@needs_fixtures
def test_parse_citations_and_staff():
    cites = parse.parse_cites(read("sonix_cites.html"))
    assert len(cites) == 6 and cites[0]["id"] == "821212" and cites[0]["pub_id"] == "140912"
    assert cites[0]["year"] == 2025
    staff = parse.parse_staff(read("sonix_new_publication.html"))
    me = [s for s in staff if s["surname"] == "Арсенов"][0]
    assert me["id"] == "6100" and me["given"] == "Нестор" and me["active"]
    assert any(not s["active"] for s in staff)


# ------------------------------------------------------------------ matching
@needs_fixtures
def test_title_matching_survives_cyrillic_lookalikes():
    pubs = parse.parse_publications(read("sonix_publications.html"))
    m = Merged(records=[], title="QUAIA X VLASS: A NEW SAMPLE OF COMPACT EXTRAGALACTIC RADIO SOURCES", dois=set())
    assert match.find_entry(m, pubs)["id"] == "163735"          # Sonix text has a Cyrillic "е" in "Nеw"
    m2 = Merged(records=[], title="Something else entirely about galaxies", dois={"10.3847/1538-4365/adf056"})
    assert match.find_entry(m2, pubs)["id"] == "160730"           # matched by DOI


@needs_fixtures
def test_existing_citation_recognised_in_other_formats():
    cites = parse.parse_cites(read("sonix_cites.html"))
    m = Merged(records=[], title="A dual-prediction framework for high-energy proton flux driven by graph neural networks",
               dois={"10.1109/access.2025.3624417"})
    assert match.find_entry(m, cites)["id"] == "899286"
    m = Merged(records=[], title="Predicting the energy spectra of solar energetic particles with a machine learning regression algorithm")
    assert match.find_entry(m, cites)["id"] == "738358"
    m = Merged(records=[], title="Predicting the energetic proton flux with a machine learning regression algorithm")
    assert match.find_entry(m, cites)["id"] == "738353"            # similar title, different paper


@needs_fixtures
def test_staff_matching_with_transliteration():
    staff = parse.parse_staff(read("sonix_new_publication.html"))
    ids = match.match_staff(["Arsenov, N.", "Kovacs, A.", "Slavcheva-Mihova, L.", "Kamen Kozarev", "Nedal, M."], staff)
    by = {s["id"]: s["surname"] for s in staff}
    assert [by.get(i, "") for i in ids] == ["Арсенов", "", "Славчева-Михова", "Козарев", "Недал"]


def test_preprint_entries_recognised():
    assert match.looks_like_preprint('Ivanov, S. "Variability". arXiv:2312.04567, 2023')
    assert match.looks_like_preprint("Smith, J. Title. arXiv e-prints, 2025")
    assert match.looks_like_preprint("Smith, J. Title. https://doi.org/10.48550/arXiv.2312.04567")
    assert not match.looks_like_preprint("Smith, J. Title. ApJ 975, 2024, arXiv:2312.04567, https://doi.org/10.3847/x")
    assert not match.looks_like_preprint('Liu, J. "Predicting the Energy Spectra". The Astrophysical Journal Letters, 975')


def test_sonix_citation_format():
    m = Merged(records=[], title="{Redshift evolution of the Hubble constant}", year=2026, kind="journal",
               authors=["Dai, Xinyi", "Yang, Yupeng", "Wang, Yicheng", "Qu, Yankun"], journal="Physical Review D",
               volume="113", pages="063514", doi="10.1103/zg3l-yt32")
    assert fmt.sonix_citation_text(m) == ('Dai, X., Yang, Y., Wang, Y., et al. "Redshift evolution of the Hubble constant". '
                                          'Physical Review D, 113, 063514, 2026')
    assert fmt.mla_name("Charlotte M. Koenig") == "Koenig, C. M."
    assert fmt.mla_name("Garcia Escudero, Helena") == "Garcia Escudero, H."


# ------------------------------------------------------------------ the real client in a real browser
needs_browser = pytest.mark.skipif(not pw_browser.available(), reason="Playwright browser not available")


@needs_browser
@needs_fixtures
def test_client_against_fake_sonix():
    with fake_sonix.FakeSonixServer() as srv:
        b = pw_browser.PlaywrightBrowser()
        try:
            client = SonixClient(b, base=srv.base, pause=0)
            with pytest.raises(SonixError):
                client.login(srv.email, "wrong")
            assert client.login(srv.email, srv.password) == "Арсенов, Нестор"
            pubs = client.publications()
            assert len(pubs) == 5
            staff = client.staff()
            assert len(staff) > 80
            new_id, missing = client.add_publication({
                "pubtypeID": "4", "authors": [("Arsenov, N.", "6100"), ("Kovacs, A.", ""), ("Slavcheva-Mihova, L.", "2401")],
                "corBAS": "Y", "authorsNum": "3", "fauthor": "Y", "year_pub": "2026", "title": "A test paper on voids",
                "description": "Astronomy & Astrophysics", "volume": "700", "issn": "0004-6361",
                "doi": "10.1051/0004-6361/2026xxxxx", "page_bgn": "A12", "pubstatusID": "2", "refID": "4",
                "sjr": "1.968", "isiif": "5.8", "url": "https://doi.org/10.1051/0004-6361/2026xxxxx", "report": "N"})
            assert new_id and not missing
            rec = srv.added_pubs[-1]
            assert rec["authors"] == ["Arsenov, N.", "Kovacs, A.", "Slavcheva-Mihova, L."]
            assert rec["userIDs"] == ["6100", "0", "2401"]
            assert rec["pubtypeID"] == "4" and rec["pubstatusID"] == "2" and rec["report"] == "N"
            assert rec["title"] == "A test paper on voids" and rec["sjr"] == "1.968"

            client.add_citation(new_id, {"descr": 'Dai, X. "Some title". Physical Review D, 113, 063514, 2026',
                                         "citeTypeID": "8", "year": "2026", "url": "https://doi.org/10.1103/x"})
            c = srv.added_cites[-1]
            assert c["pub_id"] == new_id and c["citeTypeID"] == "8" and c["year"] == "2026" and c["report"] == "Y"
            assert client.cites(new_id)[0]["text"].startswith("Dai, X.")
            old = srv.cites["140912"][2]
            client.update_citation("140912", old["id"], {"descr": 'Qiao, J., et al. "A Dual-Prediction Framework". IEEE Access, 13, 2025',
                                                         "citeTypeID": "8", "year": "2025", "url": "https://doi.org/10.1109/x",
                                                         "old_text": old["text"]})
            assert srv.updated_cites[-1]["text"].startswith("Qiao, J., et al.") and srv.updated_cites[-1]["type"] == "8"
            other = srv.cites["140912"][3]
            with pytest.raises(SonixError):           # the page doesn't show the entry we expected
                client.update_citation("140912", other["id"], {"descr": "x", "citeTypeID": "8", "year": "2025",
                                                               "old_text": "Completely different text about nothing"})
            assert other["text"].startswith("Riaño")                   # left unchanged
            with pytest.raises(SonixError):           # Sonix refuses a citation without a year
                client.add_citation(new_id, {"descr": "x", "citeTypeID": "8", "year": ""})
        finally:
            b.quit()


# ------------------------------------------------------------------ the pipeline with a stand-in Sonix
STAFF = [
    {"id": "11", "code": "X/1", "surname": "Петрова", "given": "Елена", "active": True, "label": "( X/1 ) Петрова, Елена  (Активен)"},
    {"id": "12", "code": "X/2", "surname": "Георгиев", "given": "Иван", "active": True, "label": "( X/2 ) Георгиев, Иван  (Активен)"},
]


def make_sonix():
    pubs = [
        {"id": "70", "text": "Petrova, E., Georgiev, I.. A survey of cool dwarfs in the solar neighbourhood. MNRAS, 500, 2021, "
                             "DOI:https://doi.org/10.1093/mnras/stab001", "year": 2021, "not_in_report": False, "cites": 1},
        {"id": "71", "text": "Petrova, E.. An old conference talk on dwarfs. Proc. Something, 2019", "year": 2019,
         "not_in_report": True, "cites": 0},
    ]
    cites = {"70": [{"id": "1", "pub_id": "70", "year": 2026, "not_in_report": False,
                     "text": 'Dai, Xinyi; Yang, Yupeng. "Redshift evolution of the Hubble constant: constraints and new insights '
                             'from an interacting dark energy model". Phys. Rev. D 113, 2026'},
                    {"id": "2", "pub_id": "70", "year": 2023, "not_in_report": False,
                     "text": 'Ivanov, S. "Photometric variability of red dwarfs". arXiv:2312.04567, 2023'},
                    {"id": "3", "pub_id": "70", "year": 2025, "not_in_report": False,
                     "text": 'Garcia Escudero, H. "LCDM and Beyond: Neutrinos and the Puzzle of Cosmological Tensions". '
                             'arXiv e-prints, 2025'}]}
    return fake_sonix.FakeSonixClient(pubs, cites, STAFF)


def run_job(sonix):
    job = pipeline.Job()
    job.settings = Settings(orcid=ORCID_ID, ads_token="tok", joined_year=2020, sonix_email="me@x", sonix_password="right")
    job.http = FakeHttp()
    job.make_sonix = lambda S, log: sonix
    pipeline.find_papers(job, job.http, None)
    return job


def test_papers_compared_with_sonix():
    sonix = make_sonix()
    job = run_job(sonix)
    assert job.settings.sonix_password == ""                         # dropped after sign-in
    by_title = {p["title"]: p for p in job.papers.values()}
    survey = by_title["A survey of cool dwarfs in the solar neighbourhood"]
    assert survey["in_sonix"] and survey["sonix_id"] == "70" and not survey["add"] and survey["form"] is None
    knee = by_title["Finite element model of the human knee joint under impact loading"]
    assert not knee["in_sonix"] and knee["add"]
    f = knee["form"]
    assert [a["name"] for a in f["authors"]] == ["Petrova, E.", "Dimitrov, P.", "Koleva, A."]
    assert [a["staff"] for a in f["authors"]] == ["11", "", ""]
    assert f["corBAS"] == "Y" and f["pubtypeID"] == "4" and f["doi"] == "10.1016/j.medengphy.2015.01.002"
    assert f["pubstatusID"] == ""                                     # no Scimago list: must be chosen
    only = [p for p in job.papers.values() if not p["from_orcid"]]
    assert len(only) == 1 and only[0]["sonix_id"] == "71" and not only[0]["unit_report"]


def test_citations_hide_existing_and_self_citations_then_save(tmp_path):
    sonix = make_sonix()
    job = run_job(sonix)
    ids = [pid for pid, p in job.papers.items() if p["cite"] and p["searchable"]]
    pipeline.find_citations(job, job.http, None, ids)
    pid_survey = next(pid for pid, p in job.papers.items() if p["sonix_id"] == "70")
    block = job.citations[pid_survey]
    titles = [it["title"] for it in block["items"]]
    assert block["already"] == 2 and not any(t.startswith("Redshift") for t in titles)   # Dai, and the thesis
    upd = [it for it in block["items"] if it["replace"]]
    assert [it["title"] for it in upd] == ["Photometric variability of red dwarfs"] and upd[0]["replace"] == "2"
    assert upd[0]["type"] == "8" and upd[0]["selected"] and "arXiv:2312.04567" in upd[0]["old_text"]
    assert block["updates"] == 1 and block["new"] == len(block["items"]) - 1
    assert block["self_excluded"] == 2                               # Petrova's preprint and erratum
    assert "Flare rates of nearby cool dwarfs" not in titles
    assert all(it["text"].count('"') == 2 for it in block["items"])
    pid_knee = next(pid for pid, p in job.papers.items() if p["title"].startswith("Finite"))
    kblock = job.citations[pid_knee]
    assert kblock["self_excluded"] == 1                              # shares co-author Dimitrov
    assert [it["title"] for it in kblock["items"]] == ["Modelling of knee ligaments"]

    plan = pipeline.make_plan(job)
    assert not plan["can_save"] and any("status" in p for p in plan["problems"])
    pipeline.apply_choices(job, {pid_knee: {"form": {"pubstatusID": "21"}}}, None)
    for pid, p in job.papers.items():
        if p["add"] and pid != pid_knee:
            pipeline.apply_choices(job, {pid: {"add": False}}, None)
    plan = pipeline.make_plan(job)
    assert plan["can_save"], plan["problems"]

    pipeline.save_to_sonix(job)
    res = job.save_results
    assert len(res["pubs_added"]) == 1 and not res["pubs_failed"]
    added = sonix.added_pubs[0]
    assert added["title"].startswith("Finite element") and added["report"] == "N"     # 2015, before joining in 2020
    assert added["authors"][0] == ("Petrova, E.", "11")
    new_id = res["pubs_added"][0]["id"]
    to_knee = [c for c in sonix.added_cites if c["pub_id"] == new_id]
    assert len(to_knee) == 1 and to_knee[0]["citeTypeID"] == "4"                       # Bulgarian thesis
    assert not [c for c in sonix.added_cites if c["pub_id"] == "70"]     # everything new there is an update
    assert res["cites_added"] == len(sonix.added_cites)
    assert res["cites_updated"] == 1 and sonix.updated_cites[0]["cite_id"] == "2"
    assert sonix.updated_cites[0]["citeTypeID"] == "8" and sonix.updated_cites[0]["year"] == "2024"
    assert sonix.updated_cites[0]["url"] == "https://doi.org/10.1515/baj-2024-0001"
    assert not any("Photometric" in c["descr"] for c in sonix.added_cites)     # updated, not added twice

    summary = pipeline.build_summary(job, str(tmp_path))
    assert summary["sonix_written"] and summary["citations"]["self_excluded"] == 3
    assert "self_citations_left_out.csv" in summary["files"]


def test_wrong_sonix_password_stops_early():
    job = pipeline.Job()
    job.settings = Settings(orcid=ORCID_ID, sonix_email="me@x", sonix_password="nope")
    job.http = FakeHttp()
    job.make_sonix = lambda S, log: make_sonix()
    with pytest.raises(SonixError):
        pipeline.find_papers(job, job.http, None)
    assert job.http.calls["pub.orcid.org"] == 0


def test_web_flow_with_sonix(tmp_path):
    from tonix2 import web
    sonix = make_sonix()
    app = web.create_app(root=str(tmp_path), sonix_factory=lambda S, log: sonix,
                         http_factory=lambda *a, **k: FakeHttp())
    c = app.test_client()

    def wait():
        for _ in range(200):
            st = c.get("/api/status").get_json()
            if not st["running"]:
                return st
            time.sleep(0.05)
        raise AssertionError("timeout")
    assert c.post("/api/start", json={"orcid": ORCID_ID, "sonix_email": "me@x"}).status_code == 400   # no password
    assert c.post("/api/start", json={"orcid": ORCID_ID, "sonix_email": "me@x", "sonix_password": "right",
                                      "ads_token": "tok"}).status_code == 200
    assert wait()["phase"] == "papers_ready"
    d = c.get("/api/papers").get_json()
    assert d["sonix"] and len(d["staff"]) == 2
    choices = {p["id"]: {"add": False} for p in d["papers"]}
    assert c.post("/api/citations", json={"papers": choices}).status_code == 200
    assert wait()["phase"] == "citations_ready"
    plan = c.post("/api/plan", json={"papers": choices}).get_json()
    assert plan["can_save"] and not plan["publications"]
    assert c.post("/api/save", json={"papers": choices}).status_code == 200
    st = wait()
    assert st["phase"] == "saved", st
    s = c.post("/api/finish", json={}).get_json()
    assert s["saved"]["cites_added"] == len(sonix.added_cites)
    assert s["saved"]["cites_updated"] == len(sonix.updated_cites) == 1
