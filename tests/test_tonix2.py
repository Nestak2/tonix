import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fake_api import ORCID_ID, FakeHttp  # noqa: E402
from tonix2 import classify, fmt, merge, pipeline  # noqa: E402
from tonix2.config import Settings  # noqa: E402
from tonix2.ids import name_key, norm_arxiv, norm_doi, parse_orcid  # noqa: E402
from tonix2.model import Merged, Record  # noqa: E402


# ------------------------------------------------------------------ ids
def test_doi_and_arxiv_normalisation():
    assert norm_doi("https://doi.org/10.1093/MNRAS/STAB001") == "10.1093/mnras/stab001"
    assert norm_doi("doi:10.1103/zg3l-yt32.") == "10.1103/zg3l-yt32"
    assert norm_doi("not a doi") is None
    assert norm_arxiv("arXiv:2101.00001v3") == "2101.00001"
    assert norm_arxiv("https://arxiv.org/abs/hep-th/9901001v2") == "hep-th/9901001"
    assert norm_arxiv("10.48550/arXiv.2305.12345") == "2305.12345"


def test_orcid_checksum():
    assert parse_orcid("https://orcid.org/0000-0002-1825-0097") == "0000-0002-1825-0097"
    assert parse_orcid("0000000218250097") == "0000-0002-1825-0097"
    assert parse_orcid("0000-0002-1825-0098") is None
    assert parse_orcid("0000-0002-1694-233X") == "0000-0002-1694-233X"


def test_name_keys_match_across_formats():
    assert name_key("Garcia Escudero, Helena") == name_key("Helena Garcia Escudero")
    assert name_key("Petrova, E.") == name_key("Elena Petrova")


# ------------------------------------------------------------------ merging
def test_paper_one_and_two_are_not_merged():
    a = Record("orcid", "1", title="Stellar flares in M dwarfs. I. Detection method", year=2022)
    b = Record("orcid", "2", title="Stellar flares in M dwarfs. II. Detection method", year=2023)
    assert len(merge.cluster([a, b])) == 2


def test_title_merge_refused_between_two_journal_dois():
    a = Record("orcid", "1", title="Long identical title about cool dwarf stars", year=2020, dois={"10.1/a"}, kind="proceedings")
    b = Record("orcid", "2", title="Long identical title about cool dwarf stars", year=2021, dois={"10.1/b"}, kind="journal")
    c = Record("orcid", "3", title="Long identical title about cool dwarf stars", year=2020, arxiv="2001.00001", kind="preprint")
    clusters = merge.cluster([a, b, c])
    assert len(clusters) == 2          # the preprint joins one of them, the two DOIs stay apart


def test_preprint_and_journal_merge_by_title_and_prefer_journal():
    j = Record("openalex", "W1", title="Knee joint model under impact", year=2015, dois={"10.1/x"}, kind="journal", journal="Med Eng Phys")
    p = Record("openalex", "W2", title="Knee joint model under impact", year=2014, arxiv="1401.00001", kind="preprint")
    [c] = merge.cluster([j, p])
    m = merge.summarize(c)
    assert m.kind == "journal" and m.year == 2015 and m.doi == "10.1/x" and m.arxiv == "1401.00001"


def test_erratum_never_merges_by_title():
    a = Record("ads", "1", title="A survey of cool dwarfs in the solar neighbourhood", year=2021, kind="journal", dois={"10.1/a"})
    b = Record("ads", "2", title="A survey of cool dwarfs in the solar neighbourhood", year=2022, kind="erratum")
    assert len(merge.cluster([a, b])) == 2


# ------------------------------------------------------------------ format
def test_vancouver_matches_old_csl_output():
    m = Merged(records=[], title="{Redshift evolution of the Hubble constant: Constraints and new insights from an interacting dark energy model}",
               year=2026, authors=["Dai, Xinyi", "Yang, Yupeng", "Wang, Yicheng", "Qu, Yankun", "Yi, Shuangxi"],
               doi="10.1103/zg3l-yt32", kind="journal", journal="Phys.Rev.D", volume="113", pages="063514")
    assert fmt.citation_text(m) == ("Dai X, Yang Y, Wang Y, et al. Redshift evolution of the Hubble constant: Constraints and "
                                    "new insights from an interacting dark energy model. Phys Rev D 2026;113:063514. "
                                    "https://doi.org/10.1103/zg3l-yt32.")


def test_thesis_and_preprint_text():
    t = Merged(records=[], title="{{\\ensuremath{\\Lambda}}CDM and Beyond}", year=2025, authors=["Garcia Escudero, Helena"],
               kind="thesis", thesis_degree="phd", thesis_school="UC, Irvine (main)")
    assert fmt.citation_text(t) == "Garcia Escudero H. ΛCDM and Beyond. PhD thesis. UC, Irvine (main), 2025."
    p = Merged(records=[], title="Flare rates", year=2023, authors=["Petrova, Elena"], kind="preprint", arxiv="2301.00003")
    assert fmt.citation_text(p) == "Petrova E. Flare rates. arXiv:2301.00003; 2023."


# ------------------------------------------------------------------ classify
def test_types(tmp_path):
    th = Merged(records=[], kind="thesis", thesis_degree="phd", country_codes={"BG"})
    assert classify.cite_type(th)[0] == "4"
    ms = Merged(records=[], kind="thesis", thesis_degree="master")
    code, notes, selected = classify.cite_type(ms)
    assert code == "3" and not selected
    sc_file = tmp_path / "scimagojr 2025.csv"
    sc_file.write_text('Rank;Sourceid;Title;Type;Issn;SJR;SJR Best Quartile\n1;1;"Physical Review D";journal;"24700010, 24700029";"1,523";Q1\n', encoding="utf-8")
    sc = classify.Scimago(str(tmp_path))
    assert sc.loaded
    j = Merged(records=[], kind="journal", issns={"24700010"}, journal="Physical Review D")
    assert classify.cite_type(j, sc)[0] == "8"
    other = Merged(records=[], kind="journal", issns={"13132709"}, journal="Bulgarian Astronomical Journal")
    assert classify.cite_type(other, sc)[0] == "1"


# ------------------------------------------------------------------ whole pipeline
def _job(ads_token="tok"):
    job = pipeline.Job()
    job.settings = Settings(orcid=ORCID_ID, ads_token=ads_token, joined_year=2020)
    job.http = FakeHttp()
    return job


def test_find_papers_merges_versions_and_keeps_paper_two():
    job = _job()
    pipeline.find_papers(job, job.http, None)
    titles = {p["title"]: p for p in job.papers.values()}
    assert job.stats["orcid_entries"] == 7
    assert job.stats["papers"] == 5                       # 3 ORCID entries of one paper became one
    survey = titles["A survey of cool dwarfs in the solar neighbourhood"]
    assert survey["kind"] == "journal" and survey["arxiv"] == "2101.00001" and survey["cite"]
    assert not survey["add"]                                       # nothing to add to without Sonix
    assert set(survey["sources"]) == {"ORCID", "INSPIRE", "ADS", "OpenAlex"}
    assert "I. Detection" in " ".join(titles) and "II. Detection" in " ".join(titles)
    knee = titles["Finite element model of the human knee joint under impact loading"]
    assert knee["unit_report"] is False                            # 2015 < joined 2020
    ml = titles["Machine learning photometric redshifts for faint galaxies"]
    assert ml["kind"] == "preprint" and not ml["add"]


def test_find_citations_merges_sources_and_leaves_out_self_citations():
    job = _job()
    pipeline.find_papers(job, job.http, None)
    ids = [pid for pid, p in job.papers.items() if p["cite"]]
    pipeline.find_citations(job, job.http, None, ids)
    survey = next(b for pid, b in job.citations.items() if job.papers[pid]["title"].startswith("A survey"))
    items = {it["title"]: it for it in survey["items"]}
    dai = next(v for k, v in items.items() if k.startswith("Redshift"))
    assert set(dai["sources"]) == {"INSPIRE", "ADS", "OpenAlex"} and dai["type"] == "8"
    assert dai["text"].startswith('Dai, X., Yang, Y., Wang, Y., et al. "Redshift evolution')
    assert dai["link"] == "https://doi.org/10.1103/zg3l-yt32"
    assert "Flare rates of nearby cool dwarfs" not in items                   # self-citation, left out
    assert not any(k.startswith("Erratum") for k in items)                     # by the author too
    assert survey["self_excluded"] == 2
    assert items["Photometric variability of red dwarfs"]["type"] == "8"      # assumed without Scimago list
    abstract = items["Cool dwarfs and their flares"]
    assert abstract["type"] == "0" and not abstract["selected"]
    assert survey["new"] == 4 and survey["raw"] == 9

    knee = next(b for pid, b in job.citations.items() if job.papers[pid]["title"].startswith("Finite"))
    kitems = {it["title"]: it for it in knee["items"]}
    assert "Impact biomechanics of the knee: a review" not in kitems          # shares co-author Dimitrov
    assert kitems["Modelling of knee ligaments"]["type"] == "4"


def test_without_ads_token_ads_is_never_called():
    job = _job(ads_token=None)
    pipeline.find_papers(job, job.http, None)
    pipeline.find_citations(job, job.http, None, [pid for pid, p in job.papers.items() if p["cite"]])
    assert job.http.calls["api.adsabs.harvard.edu"] == 0
    assert job.citations


def test_web_flow(tmp_path, monkeypatch):
    from tonix2 import web
    monkeypatch.setattr(web, "Http", lambda *a, **k: FakeHttp())
    app = web.create_app(root=str(tmp_path))
    c = app.test_client()
    assert c.get("/").status_code == 200
    assert c.post("/api/start", json={"orcid": "1234"}).status_code == 400
    r = c.post("/api/start", json={"orcid": ORCID_ID, "ads_token": "tok", "sonix_password": "secret"})
    assert r.status_code == 200

    def wait():
        for _ in range(100):
            st = c.get("/api/status").get_json()
            if not st["running"]:
                return st
            time.sleep(0.05)
        raise AssertionError("timeout")
    st = wait()
    assert st["phase"] == "papers_ready", st
    papers = c.get("/api/papers").get_json()["papers"]
    assert len(papers) == 5
    r = c.post("/api/citations", json={"papers": {}})
    assert r.status_code == 200
    assert wait()["phase"] == "citations_ready"
    blocks = c.get("/api/citations").get_json()["blocks"]
    first = blocks[0]["items"][0]["id"]
    s = c.post("/api/finish", json={"citations": {first: {"selected": False, "type": "1"}}}).get_json()
    assert s["citations"]["left_out"] >= 1 and not s["sonix_written"]
    for f in s["files"]:
        assert c.get(f"/api/export/{f}").status_code == 200
    # the password must not end up in any exported file
    for root, _, files in os.walk(tmp_path / "output"):
        for f in files:
            assert "secret" not in open(os.path.join(root, f), encoding="utf-8-sig").read()
