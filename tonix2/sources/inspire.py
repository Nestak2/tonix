"""INSPIRE-HEP literature API (free, no key)."""
from ..ids import is_erratum_title, norm_arxiv, norm_doi
from ..model import Record

API = "https://inspirehep.net/api/literature"
FIELDS = ("control_number,titles,authors.full_name,author_count,dois,arxiv_eprints,"
          "publication_info,document_type,thesis_info,refereed,earliest_date,imprints,preprint_date")
PAGE = 250
MAX_RESULTS = 10000           # INSPIRE does not page beyond this
_SKIP_DOI_MATERIAL = {"erratum", "addendum", "reprint", "translation", "editorial note"}


def _year(s):
    s = str(s or "")
    return int(s[:4]) if s[:4].isdigit() else None


def parse(hit):
    md = hit.get("metadata", hit)
    recid = str(md.get("control_number") or hit.get("id") or "")
    titles = md.get("titles") or []
    rec = Record(source="inspire", source_id=recid, title=(titles[0].get("title") if titles else "") or "")
    rec.url = f"https://inspirehep.net/literature/{recid}" if recid else ""
    rec.authors = [a.get("full_name", "") for a in md.get("authors") or [] if a.get("full_name")]
    rec.author_count = md.get("author_count") or len(rec.authors) or None
    for d in md.get("dois") or []:
        if (d.get("material") or "publication").lower() in _SKIP_DOI_MATERIAL:
            continue
        nd = norm_doi(d.get("value"))
        if nd and not nd.startswith("10.48550/"):
            rec.dois.add(nd)
    eprints = md.get("arxiv_eprints") or []
    if eprints:
        rec.arxiv = norm_arxiv(eprints[0].get("value"))
    rec.refereed = md.get("refereed")

    pubs = [p for p in md.get("publication_info") or [] if p.get("journal_title")]
    pub = pubs[0] if pubs else {}
    rec.journal = pub.get("journal_title", "")
    rec.volume = str(pub.get("journal_volume") or "")
    if pub.get("artid"):
        rec.pages = str(pub["artid"])
    elif pub.get("page_start"):
        rec.pages = str(pub["page_start"]) + (f"-{pub['page_end']}" if pub.get("page_end") else "")

    types = [t.lower() for t in md.get("document_type") or []]
    thesis = md.get("thesis_info") or {}
    if "thesis" in types:
        rec.kind = "thesis"
        rec.thesis_degree = (thesis.get("degree_type") or "").lower()
        inst = thesis.get("institutions") or []
        rec.thesis_school = inst[0].get("name", "") if inst else ""
        rec.year = _year(thesis.get("date") or thesis.get("defense_date"))
    elif "book chapter" in types:
        rec.kind = "chapter"
    elif "book" in types:
        rec.kind = "book"
    elif ("conference paper" in types or "proceedings" in types) and (rec.journal or rec.dois):
        rec.kind = "proceedings"
    elif rec.journal and (rec.dois or rec.volume or rec.pages):
        rec.kind = "journal"
    elif rec.arxiv:
        rec.kind = "preprint"
    if is_erratum_title(rec.title):
        rec.kind = "erratum"

    if rec.year is None:
        if rec.kind in ("journal", "proceedings") and pub.get("year"):
            rec.year = int(pub["year"])
        else:
            imprints = md.get("imprints") or []
            rec.year = _year(md.get("preprint_date")) or _year(imprints[0].get("date") if imprints else None) \
                or _year(md.get("earliest_date"))
    return rec


def _search(http, query, limit=MAX_RESULTS, progress=None):
    out, page = [], 1
    while True:
        data = http.get_json(API, {"q": query, "size": PAGE, "page": page, "fields": FIELDS, "sort": "mostrecent"})
        hits = (data or {}).get("hits", {})
        batch = hits.get("hits") or []
        out.extend(parse(h) for h in batch)
        total = hits.get("total") or 0
        if progress:
            progress(len(out), total)
        if not batch or len(out) >= min(total, limit) or page * PAGE >= MAX_RESULTS:
            return out, total
        page += 1


def find(http, doi=None, arxiv=None):
    if doi:
        q = f'doi:"{doi}"'
    elif arxiv:
        q = f"arxiv:{arxiv}"
    else:
        return []
    recs, _ = _search(http, q, limit=5)
    return recs


def citing(http, recid):
    """All records that cite INSPIRE record `recid`. Returns (records, total, truncated)."""
    recs, total = _search(http, f"refersto:recid:{recid}")
    return recs, total, total > len(recs)
