"""The work itself, run in a background thread and reported to the web page through a Job."""
import csv
import json
import os
import threading
import time
from collections import Counter
from datetime import datetime

from . import classify, fmt, merge
from .http import HttpError
from .ids import arxiv_doi, name_key, norm_doi
from .model import PUBLISHED_KINDS, Merged
from .sonix import match as smatch
from .sonix.client import SonixError
from .sources import ads, inspire, openalex, orcid

KIND_LABELS = {"journal": "Journal article", "proceedings": "Conference paper", "chapter": "Book chapter",
               "book": "Book", "thesis": "Thesis", "preprint": "Preprint only", "erratum": "Erratum",
               "other": "Other"}
SOURCE_LABELS = {"orcid": "ORCID", "inspire": "INSPIRE", "ads": "ADS", "openalex": "OpenAlex"}
COAUTHOR_FLAG_LIMIT = 50      # above this many authors the co-author check means little
MAX_AUTHORS_TYPED = 25        # longer author lists: first 10 plus the unit's authors, total in "Общ брой автори"

# Sonix select values
PUBTYPE = {"journal": "4", "proceedings": "5", "chapter": "17", "book": "1"}
PUBTYPE_LABELS = {"4": "Статия в научно списание", "5": "Статия в сборник на научен форум",
                  "3": "Студия в научно списание", "17": "Статия в тематичен сборник",
                  "16": "Студия в тематичен сборник", "2": "Глава от научна монография",
                  "1": "Научна монография", "18": "Научно съобщение"}
STATUS_LABELS = {"": "-- choose --", "1": "Q1 - оглавява ранглистата", "2": "Q1, не оглавява ранглистата",
                 "3": "Q2", "4": "Q3", "5": "Q4", "11": "SJR, непопадащ в Q категория",
                 "21": "Без JCR или SJR – индексиран в WoS или Scopus", "22": "Индексирано в ERIH+",
                 "31": "Международно академично издателство", "32": "Международно неакадемично издателство",
                 "33": "Национално академично издателство", "34": "Национално неакадемично издателство",
                 "51": "В депозитна база (напр. arxiv)", "99": "Друго"}
REF_LABELS = {"0": "--", "5": "Web of Science", "4": "Scopus", "25": "The SAO/NASA Astrophysics Data System",
              "6": "ERIH Plus", "9999": "Друга база"}
NEEDS_METRIC = {"1", "2", "3", "4", "5", "11"}      # Sonix requires JCR-IF or SJR for these
QUARTILE_STATUS = {"Q1": "2", "Q2": "3", "Q3": "4", "Q4": "5"}


class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.phase = "start"
        self.running = False
        self.error = None
        self.lines = []
        self.warnings = []
        self.progress = {"done": 0, "total": 0, "label": ""}
        self.settings = None
        self.http = None
        self.person = None
        self.started = None
        self.stats = Counter()
        self.papers = {}              # id -> dict for the page
        self.paper_objs = {}          # id -> Merged
        self.citations = {}           # paper id -> dict for the page
        self.excluded = {}            # paper id -> self-citations left out
        self.summary = None
        self.disabled = {}
        self.make_sonix = None        # callable(settings, log) -> SonixClient
        self.sonix = None
        self.sonix_pubs = []
        self.staff = []
        self.sonix_user = None
        self.save_results = None

    # ----------------------------------------------------------- reporting
    def log(self, msg, level="info"):
        stamp = datetime.now().strftime("%H:%M:%S")
        with self.lock:
            self.lines.append({"t": stamp, "level": level, "msg": msg})
            if level in ("warn", "error"):
                self.warnings.append({"level": level, "msg": msg})

    def step(self, done, total, label=None):
        with self.lock:
            self.progress = {"done": done, "total": total, "label": label or self.progress["label"]}

    def status(self):
        with self.lock:
            return {"phase": self.phase, "running": self.running, "error": self.error,
                    "progress": dict(self.progress), "log": self.lines[-300:],
                    "warnings": len(self.warnings), "sonix": bool(self.sonix)}

    def close_sonix(self):
        if self.sonix:
            try:
                self.sonix.close()
            finally:
                self.sonix = None

    # ----------------------------------------------------------- source calls
    def call(self, source, fn, *args, **kwargs):
        """Run one source call; failures become warnings instead of stopping the run."""
        if source in self.disabled:
            return None
        try:
            return fn(*args, **kwargs)
        except HttpError as exc:
            self.stats[f"errors_{source}"] += 1
            msg = str(exc)
            if "refused access" in msg:
                if source == "openalex" and not (self.settings and self.settings.openalex_key):
                    msg = ("OpenAlex's daily allowance without a key is used up. Get a free key at "
                           "openalex.org/settings/api and enter it on the start page")
                self.disabled[source] = msg
                self.log(f"{SOURCE_LABELS[source]} switched off for this run: {msg}", "warn")
            elif self.stats[f"errors_{source}"] <= 3:
                self.log(f"{SOURCE_LABELS[source]}: {msg}", "warn")
            if self.stats[f"errors_{source}"] >= 8 and source not in self.disabled:
                self.disabled[source] = "too many failures"
                self.log(f"{SOURCE_LABELS[source]} switched off after repeated failures", "warn")
            return None


def run_in_thread(job, target, *args):
    def wrapper():
        try:
            target(job, *args)
        except Exception as exc:  # report anything unexpected on the page
            msg = str(exc) if isinstance(exc, SonixError) or type(exc).__name__ == "BrowserError" \
                else f"{type(exc).__name__}: {exc}"
            with job.lock:
                job.error = msg
            job.log(f"Stopped: {msg}", "error")
        finally:
            with job.lock:
                job.running = False
    with job.lock:
        job.running = True
        job.error = None
    threading.Thread(target=wrapper, daemon=True).start()


def _short_authors(authors, count):
    return fmt.authors_text(authors, count).replace(", et al", " et al.")


# =================================================================== papers
def _lookup(job, http, dois, arxivs, bibcodes=()):
    """Find works in INSPIRE, ADS and OpenAlex by DOI / arXiv ID / bibcode."""
    S = job.settings
    use_ads = bool(S.ads_token)
    found = []
    lookups = [("doi", d) for d in sorted(dois)] + [("arxiv", a) for a in sorted(arxivs)]
    oa = job.call("openalex", openalex.find_by_dois, http,
                  sorted(dois) + [arxiv_doi(a) for a in sorted(arxivs)], S.openalex_key, S.contact_email) or {}
    found.extend(oa.values())
    for n, (kind, value) in enumerate(lookups, 1):
        job.step(n - 1, len(lookups), "Looking up your papers in INSPIRE, ADS and OpenAlex")
        found += job.call("inspire", inspire.find, http, **{kind: value}) or []
        if use_ads:
            found += job.call("ads", ads.find, http, S.ads_token, **{kind: value}) or []
    if use_ads:
        known = {r.source_id for r in found if r.source == "ads"}
        for b in sorted(set(bibcodes) - known):
            found += job.call("ads", ads.find, http, S.ads_token, bibcode=b) or []
    job.step(len(lookups), len(lookups))
    return found


def find_papers(job, http, scimago):
    S = job.settings
    job.phase = "papers"
    job.started = time.time()

    if S.sonix_email:
        job.step(0, 1, "Signing in to Sonix")
        job.sonix = job.make_sonix(S, job.log)
        job.sonix_user = job.sonix.login(S.sonix_email, S.sonix_password)
        S.sonix_password = ""                                   # not needed any more
        job.log(f"Sonix: signed in as {job.sonix_user or 'unknown user'}")
        job.step(0, 1, "Reading your Sonix publications")
        job.sonix_pubs = job.sonix.publications()
        job.staff = job.sonix.staff()
        job.log(f"Sonix: {len(job.sonix_pubs)} publications, {len(job.staff)} people in the unit's author list")
    else:
        job.log("No Sonix login given: papers and citations are found and reviewed, nothing is compared or saved")

    job.step(0, 1, "Reading your ORCID record")
    person, recs = orcid.fetch_record(http, S.orcid)
    job.person = person
    job.stats["orcid_entries"] = len(recs)
    job.log(f"ORCID: {len(recs)} work entries for {person.display}")
    if not recs:
        job.log("Your ORCID record lists no public works. Check its visibility settings in ORCID.", "warn")

    dois, arxivs, bibcodes = set(), set(), set()
    for r in recs:
        dois |= r.dois
        if r.arxiv:
            arxivs.add(r.arxiv)
        if r.ext.get("bibcode"):
            bibcodes.add(r.ext["bibcode"])
    if not S.ads_token:
        job.log("ADS: no token given, ADS is skipped")
    pool = merge.dedupe_records(list(recs) + _lookup(job, http, dois, arxivs, bibcodes))
    clusters = [c for c in merge.cluster(pool) if any(r.source == "orcid" for r in c)]
    papers = [merge.summarize(c) for c in clusters]
    job.stats["orcid_duplicates"] = sum(sum(1 for r in m.records if r.source == "orcid") - 1 for m in papers)

    # ---- which of them Sonix already has
    matched = {}
    free = list(job.sonix_pubs)
    for m in papers:
        e = smatch.find_entry(m, free, extra_ids=m.handles("ads"))
        if e:
            matched[id(m)] = e
            free.remove(e)

    # ---- Sonix entries that are not in ORCID: still search their citations
    sonix_only = []
    if free:
        job.log(f"Sonix: {len(free)} publications not found in your ORCID record")
        for e in free:
            e_dois, e_arx = smatch.ids_in_text(e["text"])
            found = _lookup(job, http, e_dois, e_arx) if (e_dois or e_arx) else []
            m = None
            for c in merge.cluster(merge.dedupe_records(found)):
                cand = merge.summarize(c)
                if (cand.dois & e_dois) or (cand.arxiv and cand.arxiv in e_arx):
                    m = cand
                    break
            if m is None:
                m = Merged(records=[], title=e["text"], year=e["year"], kind="journal", dois=set(e_dois))
                m.doi = sorted(e_dois)[0] if e_dois else None
            matched[id(m)] = e
            sonix_only.append(m)

    orcid_ids = {id(m) for m in papers}
    allp = papers + sonix_only
    allp.sort(key=lambda m: (-(m.year or 0), m.title.lower()))
    job.papers, job.paper_objs = {}, {}
    for i, m in enumerate(allp, 1):
        pid = f"P{i}"
        job.paper_objs[pid] = m
        job.papers[pid] = _paper_view(job, pid, m, matched.get(id(m)), scimago, from_orcid=id(m) in orcid_ids)
    job.stats["papers"] = len(papers)
    job.stats["preprint_only"] = sum(1 for m in papers if m.kind == "preprint")
    job.stats["in_sonix"] = sum(1 for p in job.papers.values() if p["in_sonix"])
    job.stats["sonix_only"] = len(sonix_only)
    job.log(f"{len(papers)} distinct papers in ORCID after merging {job.stats['orcid_duplicates']} duplicate entries"
            + (f"; {job.stats['in_sonix']} of all papers are already in Sonix" if job.sonix else ""))
    job.phase = "papers_ready"


def _issn_text(issns):
    for i in sorted(issns):
        return f"{i[:4]}-{i[4:]}"
    return ""


def _sonix_form(job, m, scimago):
    S = job.settings
    hit = scimago.lookup(m.issns, m.journal) if (scimago is not None and scimago.loaded) else None
    status, ref, sjr = "", "0", ""
    if m.kind == "preprint":
        status = "51"
    elif hit:
        sjr = hit["sjr"]
        status = QUARTILE_STATUS.get(hit["quartile"], "11")
        ref = "4"
    staff_ids = smatch.match_staff(m.authors, job.staff, job.sonix_user, job.person.name_variants() if job.person else ())
    total = max(m.author_count or 0, len(m.authors))
    rows = list(zip(m.authors, staff_ids))
    if len(rows) > MAX_AUTHORS_TYPED:
        rows = rows[:10] + [r for r in rows[10:] if r[1]]
    authors_known = bool(rows)
    if not rows and job.person:
        me = job.person.name_variants()[0] if job.person.name_variants() else job.person.display
        rows = [(me, smatch.match_staff([me], job.staff, job.sonix_user, job.person.name_variants())[0])]
    foreign_cc = m.country_codes - {"BG"}
    pages = (m.pages or "").split("-", 1)
    return {
        "pubtypeID": PUBTYPE.get(m.kind, "4"),
        "pubstatusID": status, "refID": ref, "isiif": "", "sjr": sjr,
        "corBAS": "Y" if rows and rows[0][1] else "N",
        "fauthor": "Y" if foreign_cc or any(not s for s in staff_ids) else "N",
        "authors": [{"name": fmt.mla_name(a)[:30], "staff": s} for a, s in rows],
        "authorsNum": str(total or len(rows)),
        "year_pub": str(m.year or ""), "title": fmt.clean_title(m.title), "description": m.journal or "",
        "volume": m.volume or "", "issn": _issn_text(m.issns), "doi": m.doi or "",
        "page_bgn": pages[0] if pages[0] else "", "page_end": pages[1] if len(pages) > 1 else "",
        "url": m.link(), "note": "",
        "sjr_quartile": hit["quartile"] if hit else "",
        "authors_known": authors_known,
    }


def _paper_view(job, pid, m, entry, scimago, from_orcid=True):
    notes = []
    orcid_n = sum(1 for r in m.records if r.source == "orcid")
    kinds = {r.kind for r in m.records if r.source == "orcid"}
    if orcid_n > 1:
        if "preprint" in kinds and kinds & set(PUBLISHED_KINDS):
            notes.append(f"{orcid_n} ORCID entries merged: preprint and published version")
        else:
            notes.append(f"{orcid_n} ORCID entries merged")
    searchable = any(m.handles(s) for s in ("inspire", "ads", "openalex"))
    if not searchable:
        notes.append("Not found in INSPIRE, ADS or OpenAlex: citations can't be searched"
                     + ("" if from_orcid or m.doi else " (the Sonix entry has no DOI)"))
    if m.kind == "preprint":
        notes.append("No journal version found")
    if m.kind == "thesis":
        notes.append("Own theses belong in Sonix's Dissertations section")
    if not from_orcid:
        notes.append("In Sonix but not in your ORCID record")
    S = job.settings
    published = m.kind in PUBLISHED_KINDS
    unit = True if not S.joined_year or not m.year else m.year >= S.joined_year
    in_sonix = entry is not None
    view = {
        "id": pid, "title": fmt.clean_title(m.title) if from_orcid or m.records else m.title,
        "year": m.year, "kind": m.kind, "kind_label": KIND_LABELS.get(m.kind, m.kind),
        "journal": m.journal, "volume": m.volume, "pages": m.pages, "doi": m.doi, "arxiv": m.arxiv,
        "link": m.link(), "authors": _short_authors(m.authors, m.author_count), "author_count": m.author_count,
        "sources": [SOURCE_LABELS[s] for s in m.sources], "notes": notes, "searchable": searchable,
        "from_orcid": from_orcid, "in_sonix": in_sonix,
        "sonix_id": entry["id"] if entry else None,
        "sonix_url": (job.sonix.base + f"/bg/258/{entry['id']}/staff/publication") if (entry and job.sonix) else None,
        "sonix_text": entry["text"] if entry else "",
        "sonix_cites": entry["cites"] if entry else 0,
        "add": published and not in_sonix and bool(job.sonix),
        "unit_report": (not entry["not_in_report"]) if entry else (unit and published),
        "cite": searchable and (published or in_sonix),
        "form": None, "sjr": None,
    }
    if not in_sonix:
        form = _sonix_form(job, m, scimago) if job.person else None
        view["form"] = form
        if form and form["sjr"]:
            view["sjr"] = {"value": form["sjr"], "quartile": form["sjr_quartile"]}
    return view


# =================================================================== citations
def _self_keys(job, paper):
    mine = {k for k in (name_key(n) for n in job.person.name_variants()) if k} if job.person else set()
    coauthors = set()
    if paper.author_count and paper.author_count <= COAUTHOR_FLAG_LIMIT:
        coauthors = {k for k in (name_key(a) for a in paper.authors) if k} - mine
    return mine, coauthors


def find_citations(job, http, scimago, paper_ids):
    S = job.settings
    job.phase = "citations"
    job.citations, job.excluded = {}, {}
    use_ads = bool(S.ads_token)
    for n, pid in enumerate(paper_ids, 1):
        paper = job.paper_objs[pid]
        view = job.papers[pid]
        label = fmt.clean_title(paper.title)[:70]
        job.step(n - 1, len(paper_ids), f"Citations for paper {n} of {len(paper_ids)}: {label}")
        raw, counts, notes = [], Counter(), []
        for recid in paper.handles("inspire"):
            got = job.call("inspire", inspire.citing, http, recid)
            if got:
                recs, total, truncated = got
                raw += recs
                counts["inspire"] += len(recs)
                if truncated:
                    notes.append(f"INSPIRE lists {total} citations; only the first {len(recs)} were read")
        if use_ads and paper.handles("ads"):
            got = job.call("ads", ads.citing, http, S.ads_token, paper.handles("ads"))
            if got:
                raw += got[0]
                counts["ads"] += len(got[0])
        if paper.handles("openalex"):
            got = job.call("openalex", openalex.citing, http, paper.handles("openalex"), S.openalex_key, S.contact_email)
            if got:
                raw += got[0]
                counts["openalex"] += len(got[0])
        for src in ("inspire", "ads", "openalex"):
            if paper.handles(src) and src in job.disabled:
                notes.append(f"{SOURCE_LABELS[src]} was switched off, so citations from it are missing")

        existing = []
        if job.sonix and view["in_sonix"] and view["sonix_cites"]:
            existing = job.sonix.cites(view["sonix_id"])

        own = set().union(*(r.keys() for r in paper.records)) if paper.records else {"doi:" + d for d in paper.dois}
        raw = [r for r in merge.dedupe_records(raw) if not (r.keys() & own)]
        mine, coauthors = _self_keys(job, paper)
        items, selfs, already, matched_existing = [], [], 0, set()
        for c in merge.cluster(raw):
            m = merge.summarize(c)
            keys = {k for k in (name_key(a) for a in m.authors) if k}
            if keys & (mine | coauthors):
                selfs.append({"title": fmt.clean_title(m.title), "year": m.year, "doi": m.doi,
                              "by": "you" if keys & mine else "co-author", "text": fmt.sonix_citation_text(m)})
                continue
            e = smatch.find_entry(m, existing, extra_ids=m.handles("ads")) if existing else None
            replace = None
            if e:
                matched_existing.add(e["id"])
                published_now = m.kind in PUBLISHED_KINDS and m.doi and not m.doi.startswith("10.48550/")
                if published_now and smatch.looks_like_preprint(e["text"]) and not smatch.mentions(e["text"], m.journal):
                    replace = e
                else:
                    already += 1
                    continue
            code, cnotes, selected = classify.cite_type(m, scimago)
            if replace:
                cnotes = ["In Sonix as the arXiv preprint: this updates that entry to the journal version"] + cnotes
            if len(c) > len({r.source for r in c}):
                cnotes = cnotes + ["Several versions merged (e.g. preprint and journal)"]
            items.append({
                "title": fmt.clean_title(m.title), "text": fmt.sonix_citation_text(m), "year": m.year,
                "type": code, "notes": cnotes, "kind": m.kind,
                "sources": [SOURCE_LABELS[s] for s in m.sources], "link": m.link(),
                "doi": m.doi, "arxiv": m.arxiv, "selected": selected and bool(m.year),
                "replace": replace["id"] if replace else None, "old_text": replace["text"] if replace else "",
            })
            if not m.year:
                items[-1]["notes"] = items[-1]["notes"] + ["Year unknown: Sonix requires one"]
        items.sort(key=lambda x: (-(x["year"] or 0), x["title"].lower()))
        for k, it in enumerate(items, 1):
            it["id"] = f"{pid}-C{k}"
        job.excluded[pid] = selfs
        multi = sum(1 for it in items if len(it["sources"]) > 1)
        job.citations[pid] = {
            "paper_id": pid, "counts": {SOURCE_LABELS[s]: v for s, v in counts.items()},
            "raw": sum(counts.values()), "unique": len(items) + already + len(selfs),
            "new": sum(1 for it in items if not it["replace"]), "updates": sum(1 for it in items if it["replace"]),
            "already": already, "self_excluded": len(selfs), "sonix_total": len(existing),
            "sonix_unmatched": len(existing) - len(matched_existing), "multi_source": multi,
            "notes": notes, "items": items,
        }
        for note in notes:
            job.log(note, "warn")
        n_up = job.citations[pid]["updates"]
        job.log(f"{label}: {len(items) - n_up} new, {n_up} to update from arXiv to journal, "
                f"{already} already in Sonix, {len(selfs)} self-citations left out")
    job.step(len(paper_ids), len(paper_ids))
    job.phase = "citations_ready"


# =================================================================== saving
def apply_choices(job, paper_choices, citation_choices):
    for pid, ch in (paper_choices or {}).items():
        p = job.papers.get(pid)
        if not p:
            continue
        for k in ("add", "unit_report", "cite"):
            if k in ch and not (p["in_sonix"] and k in ("add", "unit_report")):
                p[k] = bool(ch[k])
        if p["form"] and isinstance(ch.get("form"), dict):
            for k, v in ch["form"].items():
                if k == "authors" and isinstance(v, list):
                    p["form"]["authors"] = [{"name": str(a.get("name", ""))[:30], "staff": str(a.get("staff") or "")}
                                            for a in v if str(a.get("name", "")).strip()]
                elif k in p["form"] and k not in ("authors", "authors_known", "sjr_quartile"):
                    p["form"][k] = str(v)
    for pid, block in job.citations.items():
        for it in block["items"]:
            ch = (citation_choices or {}).get(it["id"])
            if ch:
                it["selected"] = bool(ch.get("selected", it["selected"]))
                it["type"] = str(ch.get("type", it["type"]))


def make_plan(job):
    pubs, cites, problems, warns, skipped = [], [], [], [], 0
    staff_ids = {s["id"] for s in job.staff}
    for pid, p in job.papers.items():
        if not (p["add"] and not p["in_sonix"] and p["form"]):
            continue
        f = p["form"]
        short = p["title"][:60]
        if not f["title"].strip():
            problems.append(f"“{short}”: the title is empty")
        if not f["pubstatusID"]:
            problems.append(f"“{short}”: choose the status of the journal (Статус на изданието)")
        if f["pubstatusID"] in NEEDS_METRIC and not (f["isiif"].strip() or f["sjr"].strip()):
            problems.append(f"“{short}”: Sonix needs the JCR-IF or the SJR for this status")
        if not f.get("authors_known", True):
            warns.append(f"“{short}”: the databases don't list its authors, so only you are filled in. "
                         "Add the others in the Sonix fields or in Sonix afterwards")
        if not any(a["staff"] in staff_ids for a in f["authors"]):
            problems.append(f"“{short}”: at least one author must be linked to a person of your unit")
        pubs.append({"pid": pid, "title": p["title"]})
    for pid, block in job.citations.items():
        p = job.papers[pid]
        chosen = [it for it in block["items"] if it["selected"]]
        if not chosen:
            continue
        if not (p["in_sonix"] or p["add"]):
            skipped += len(chosen)
            continue
        for it in chosen:
            if not it["year"]:
                problems.append(f"Citation “{it['title'][:50]}” has no year")
            if it["type"] == "0":
                problems.append(f"Citation “{it['title'][:50]}”: choose its type")
        n_up = sum(1 for it in chosen if it.get("replace"))
        cites.append({"pid": pid, "title": p["title"], "count": len(chosen) - n_up, "updates": n_up,
                      "new_paper": not p["in_sonix"]})
    return {"publications": pubs, "citations": cites, "problems": problems, "warnings": warns,
            "citations_total": sum(c["count"] for c in cites), "updates_total": sum(c["updates"] for c in cites),
            "skipped_not_in_sonix": skipped,
            "can_save": bool(job.sonix) and not problems and bool(pubs or cites)}


def _pub_fields(p):
    f = dict(p["form"])
    f["authors"] = [(a["name"], a["staff"]) for a in f["authors"]]
    f["report"] = "Y" if p["unit_report"] else "N"
    f.pop("sjr_quartile", None)
    f.pop("authors_known", None)
    return f


def save_to_sonix(job):
    plan = make_plan(job)
    if plan["problems"]:
        raise SonixError("Fix these first: " + "; ".join(plan["problems"][:3]))
    job.phase = "saving"
    client = job.sonix
    res = {"pubs_added": [], "pubs_failed": [], "cites_added": 0, "cites_updated": 0, "cites_failed": [],
           "cites_skipped": 0}
    total = len(plan["publications"]) + plan["citations_total"] + plan["updates_total"]
    done, fails_in_row = 0, 0

    def failed_again():
        nonlocal fails_in_row
        fails_in_row += 1
        if fails_in_row >= 3:
            raise SonixError("Sonix refused three entries in a row; stopped to be safe. Already saved entries stay saved.")

    for item in plan["publications"]:
        p = job.papers[item["pid"]]
        job.step(done, total, f"Adding publication: {p['title'][:70]}")
        try:
            new_id, missing = client.add_publication(_pub_fields(p))
            if not new_id:
                entry = smatch.find_entry(job.paper_objs[item["pid"]], client.publications())
                new_id = entry["id"] if entry else None
            if missing:
                job.log(f"“{p['title'][:60]}”: Sonix's form had no field for {', '.join(missing)}", "warn")
            p.update(in_sonix=True, sonix_id=new_id, add=False)
            res["pubs_added"].append({"title": p["title"], "id": new_id})
            job.log(f"Added publication “{p['title'][:70]}”" + (f" (Sonix id {new_id})" if new_id else ""))
            fails_in_row = 0
        except SonixError as exc:
            res["pubs_failed"].append({"title": p["title"], "error": str(exc)})
            job.log(f"Could not add “{p['title'][:60]}”: {exc}", "error")
            failed_again()
        done += 1

    for c in plan["citations"]:
        p = job.papers[c["pid"]]
        chosen = [it for it in job.citations[c["pid"]]["items"] if it["selected"] and not it.get("saved")]
        if not p.get("sonix_id"):
            res["cites_skipped"] += len(chosen)
            job.log(f"Citations of “{p['title'][:60]}” skipped: the publication is not in Sonix", "warn")
            done += len(chosen)
            continue
        for it in chosen:
            job.step(done, total, f"Adding citations to: {p['title'][:60]}")
            fields = {"descr": it["text"], "citeTypeID": it["type"], "year": str(it["year"]), "url": it["link"],
                      "report": "Y"}
            try:
                if it.get("replace"):
                    client.update_citation(p["sonix_id"], it["replace"], dict(fields, old_text=it["old_text"]))
                    res["cites_updated"] += 1
                    job.log(f"Updated to the journal version: “{it['title'][:60]}”")
                else:
                    client.add_citation(p["sonix_id"], fields)
                    res["cites_added"] += 1
                it["saved"] = True
                fails_in_row = 0
            except SonixError as exc:
                res["cites_failed"].append({"paper": p["title"], "citation": it["text"][:120], "error": str(exc)})
                job.log(f"Could not add citation “{it['title'][:50]}”: {exc}", "error")
                failed_again()
            done += 1
        job.log(f"“{p['title'][:60]}”: citations saved")
    job.step(total, total)
    job.save_results = res
    job.log(f"Saved to Sonix: {len(res['pubs_added'])} publications, {res['cites_added']} new citations, "
            f"{res['cites_updated']} citations updated to the journal version")
    job.phase = "saved"


def save_job(job):
    try:
        save_to_sonix(job)
    finally:
        if job.save_results is None:
            job.save_results = {"pubs_added": [], "pubs_failed": [], "cites_added": 0, "cites_updated": 0,
                                "cites_failed": [], "cites_skipped": 0}


# =================================================================== summary
def build_summary(job, out_root):
    papers = list(job.papers.values())
    cites = [dict(it, paper_id=pid) for pid, b in job.citations.items() for it in b["items"]]
    chosen = [c for c in cites if c["selected"]]
    by_source = Counter()
    for block in job.citations.values():
        by_source.update(block["counts"])
    per_paper = []
    for pid, block in job.citations.items():
        per_paper.append({"paper": job.papers[pid]["title"], "year": job.papers[pid]["year"],
                          "new": block["new"], "updates": block["updates"],
                          "chosen": sum(1 for c in chosen if c["paper_id"] == pid),
                          "already": block["already"], "self": block["self_excluded"],
                          "saved": sum(1 for it in block["items"] if it.get("saved")),
                          "records": block["raw"], "counts": block["counts"]})
    per_paper.sort(key=lambda x: -(x["new"] + x["already"]))
    res = job.save_results
    elapsed = int(time.time() - job.started) if job.started else 0
    summary = {
        "person": job.person.display if job.person else "",
        "orcid": job.settings.orcid, "elapsed_s": elapsed,
        "sonix_connected": bool(job.sonix_user), "sonix_user": job.sonix_user,
        "papers": {
            "orcid_entries": job.stats["orcid_entries"], "distinct": job.stats["papers"],
            "duplicates_merged": job.stats["orcid_duplicates"], "preprint_only": job.stats["preprint_only"],
            "in_sonix_before": job.stats["in_sonix"], "sonix_only": job.stats["sonix_only"],
            "to_add": sum(1 for p in papers if p["add"]),
            "searched": len(job.citations),
        },
        "citations": {
            "records": sum(by_source.values()), "by_source": dict(by_source),
            "new": sum(1 for c in cites if not c.get("replace")),
            "updates": sum(1 for c in cites if c.get("replace")),
            "already_in_sonix": sum(b["already"] for b in job.citations.values()),
            "self_excluded": sum(b["self_excluded"] for b in job.citations.values()),
            "multi_source": sum(b["multi_source"] for b in job.citations.values()),
            "chosen": len(chosen), "left_out": len(cites) - len(chosen),
            "by_type": {classify.TYPE_LABELS.get(k, k): v for k, v in Counter(c["type"] for c in chosen).most_common()},
            "years": dict(sorted(Counter(c["year"] for c in chosen if c["year"]).items())),
        },
        "saved": res,
        "sonix_written": bool(res and (res["pubs_added"] or res["cites_added"] or res.get("cites_updated"))),
        "per_paper": per_paper,
        "requests": dict(job.http.calls) if job.http else {},
        "disabled_sources": {SOURCE_LABELS[k]: v for k, v in job.disabled.items()},
        "warnings": list(job.warnings),
    }
    folder = os.path.join(out_root, "run-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(folder, exist_ok=True)
    rows = []
    for p in papers:
        r = dict(p)
        r.pop("form", None)
        rows.append(r)
    _write_csv(os.path.join(folder, "papers.csv"), rows,
               ["id", "in_sonix", "sonix_id", "add", "unit_report", "cite", "year", "kind_label", "title", "authors",
                "author_count", "journal", "volume", "pages", "doi", "arxiv", "sources", "notes"])
    _write_csv(os.path.join(folder, "citations.csv"), cites,
               ["paper_id", "id", "selected", "saved", "replace", "type", "year", "text", "old_text", "link", "doi",
                "arxiv", "sources", "notes"])
    selfs = [dict(s, paper=job.papers[pid]["title"]) for pid, lst in job.excluded.items() for s in lst]
    _write_csv(os.path.join(folder, "self_citations_left_out.csv"), selfs, ["paper", "by", "year", "text", "doi"])
    with open(os.path.join(folder, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(folder, "log.txt"), "w", encoding="utf-8") as fh:
        for line in job.lines:
            fh.write(f"{line['t']} [{line['level']}] {line['msg']}\n")
    summary["folder"] = os.path.abspath(folder)
    summary["files"] = ["papers.csv", "citations.csv", "self_citations_left_out.csv", "summary.json", "log.txt"]
    job.summary = summary
    job.phase = "done"
    return summary


def _write_csv(path, rows, cols):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            w.writerow(["; ".join(map(str, r.get(c))) if isinstance(r.get(c), list) else r.get(c, "") for c in cols])
