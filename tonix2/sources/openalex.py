"""OpenAlex works API. Works without a key on a small daily budget; a free key gives 10x more."""
from ..ids import arxiv_from_url, is_erratum_title, norm_doi, split_dois, norm_issn
from ..model import Record

API = "https://api.openalex.org"
SELECT = "id,doi,display_name,publication_year,type,primary_location,locations,authorships,biblio"
PER_PAGE = 100


def _short_id(url):
    return (url or "").rsplit("/", 1)[-1]


def parse(w):
    wid = _short_id(w.get("id"))
    rec = Record(source="openalex", source_id=wid, title=w.get("display_name") or w.get("title") or "")
    rec.url = f"https://openalex.org/{wid}" if wid else ""
    rec.year = w.get("publication_year")
    dois, arxiv = split_dois([w.get("doi")])
    rec.dois = dois
    rec.arxiv = arxiv
    for loc in w.get("locations") or []:
        if rec.arxiv:
            break
        rec.arxiv = arxiv_from_url(loc.get("landing_page_url")) or arxiv_from_url(loc.get("pdf_url"))
    auths = w.get("authorships") or []
    rec.authors = [(a.get("author") or {}).get("display_name") or a.get("raw_author_name") or "" for a in auths]
    rec.authors = [a for a in rec.authors if a]
    rec.author_count = len(rec.authors) or None
    for a in auths:
        for inst in a.get("institutions") or []:
            if inst.get("country_code"):
                rec.country_codes.add(inst["country_code"].upper())

    prim = w.get("primary_location") or {}
    src = prim.get("source") or {}
    src_type = (src.get("type") or "").lower()
    src_name = src.get("display_name") or ""
    rec.issns = {i for i in (norm_issn(x) for x in (src.get("issn") or [])) if i}
    bib = w.get("biblio") or {}
    rec.volume = str(bib.get("volume") or "")
    fp, lp = bib.get("first_page"), bib.get("last_page")
    rec.pages = f"{fp}-{lp}" if fp and lp and fp != lp else str(fp or "")

    wtype = (w.get("type") or "").lower()
    is_repo = src_type == "repository" or "arxiv" in src_name.lower()
    if wtype == "dissertation":
        kind = "thesis"
        first = auths[0] if auths else {}
        insts = first.get("institutions") or []
        rec.thesis_school = insts[0].get("display_name", "") if insts else ""
    elif wtype == "erratum":
        kind = "erratum"
    elif wtype == "preprint" or (is_repo and not rec.dois):
        kind = "preprint"
    elif wtype == "book-chapter":
        kind = "chapter"
    elif wtype == "book":
        kind = "book"
    elif wtype in ("article", "review", "letter", "editorial", ""):
        kind = "proceedings" if src_type == "conference" else ("journal" if src_type in ("journal", "book series") or rec.dois else "other")
    else:
        kind = "other"           # dataset, paratext, peer-review, ...
    if kind in ("journal", "proceedings", "chapter", "book"):
        rec.journal = src_name
    if is_erratum_title(rec.title):
        kind = "erratum"
    rec.kind = kind
    return rec


def _params(key, mailto, **extra):
    p = {"api_key": key, "mailto": mailto}
    p.update(extra)
    return p


def find_by_doi(http, doi, key=None, mailto=None):
    d = norm_doi(doi)
    if not d:
        return None
    w = http.get_json(f"{API}/works/doi:{d}", _params(key, mailto, select=SELECT))
    return parse(w) if w else None


def citing(http, work_ids, key=None, mailto=None):
    out, cursor, total = [], "*", 0
    flt = "cites:" + "|".join(work_ids)
    while cursor:
        data = http.get_json(f"{API}/works", _params(key, mailto, filter=flt, select=SELECT,
                                                    per_page=PER_PAGE, cursor=cursor))
        data = data or {}
        out.extend(parse(w) for w in data.get("results") or [])
        meta = data.get("meta") or {}
        total = meta.get("count") or total
        cursor = meta.get("next_cursor") if data.get("results") else None
    return out, total


def find_by_dois(http, dois, key=None, mailto=None, chunk=50):
    """Look up many DOIs with few requests. Returns {doi: Record}."""
    wanted = [d for d in (norm_doi(x) for x in dois) if d]
    out = {}
    for i in range(0, len(wanted), chunk):
        part = wanted[i:i + chunk]
        data = http.get_json(f"{API}/works", _params(key, mailto, filter="doi:" + "|".join(part),
                                                    select=SELECT, per_page=PER_PAGE))
        for w in (data or {}).get("results") or []:
            d = norm_doi(w.get("doi"))
            if d:
                out[d] = parse(w)
    return out
