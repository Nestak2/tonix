"""NASA ADS search API (optional; needs a personal token)."""
from ..ids import is_erratum_title, norm_arxiv, norm_doi, norm_issn
from ..model import Record

API = "https://api.adsabs.harvard.edu/v1/search/query"
FL = "bibcode,title,author,author_count,year,doi,identifier,pub,volume,page,doctype,property,issn,aff"
ROWS = 2000

_DOCTYPE_KIND = {
    "article": "journal", "eprint": "preprint", "inproceedings": "proceedings", "proceedings": "proceedings",
    "abstract": "other", "inbook": "chapter", "book": "book", "phdthesis": "thesis", "mastersthesis": "thesis",
    "erratum": "erratum",
}


def parse(doc):
    bibcode = doc.get("bibcode", "")
    title = (doc.get("title") or [""])[0]
    rec = Record(source="ads", source_id=bibcode, title=title)
    rec.url = f"https://ui.adsabs.harvard.edu/abs/{bibcode}/abstract" if bibcode else ""
    rec.authors = list(doc.get("author") or [])
    rec.author_count = doc.get("author_count") or len(rec.authors) or None
    y = str(doc.get("year") or "")
    rec.year = int(y) if y.isdigit() else None
    for d in doc.get("doi") or []:
        nd = norm_doi(d)
        if nd and not nd.startswith("10.48550/"):
            rec.dois.add(nd)
    for ident in doc.get("identifier") or []:
        if str(ident).lower().startswith("arxiv:"):
            rec.arxiv = norm_arxiv(ident)
            break
    rec.issns = {i for i in (norm_issn(x) for x in doc.get("issn") or []) if i}
    props = {p.upper() for p in doc.get("property") or []}
    rec.refereed = True if "REFEREED" in props else (False if "NOT REFEREED" in props else None)
    pub = doc.get("pub") or ""
    rec.volume = str(doc.get("volume") or "")
    rec.pages = str((doc.get("page") or [""])[0] or "")
    rec.ext["bibcode"] = bibcode

    doctype = (doc.get("doctype") or "").lower()
    kind = _DOCTYPE_KIND.get(doctype, "other")
    if kind == "journal" and ("arxiv" in pub.lower() or not (rec.dois or rec.volume)):
        kind = "preprint" if rec.arxiv else "other"
    if kind == "thesis":
        rec.thesis_degree = "phd" if doctype == "phdthesis" else "master"
        aff = doc.get("aff") or []
        rec.thesis_school = aff[0] if aff and aff[0] != "-" else ""
    elif kind != "preprint":
        rec.journal = pub
    if is_erratum_title(title):
        kind = "erratum"
    rec.kind = kind
    return rec


def _query(http, token, q, rows=ROWS):
    out, start = [], 0
    headers = {"Authorization": f"Bearer {token}"}
    while True:
        data = http.get_json(API, {"q": q, "fl": FL, "rows": rows, "start": start}, headers=headers)
        resp = (data or {}).get("response", {})
        docs = resp.get("docs") or []
        out.extend(parse(d) for d in docs)
        total = resp.get("numFound") or 0
        start += len(docs)
        if not docs or start >= total:
            return out, total


def find(http, token, doi=None, arxiv=None, bibcode=None):
    if bibcode:
        q = f'bibcode:"{bibcode}"'
    elif doi:
        q = f'identifier:"{doi}"'
    elif arxiv:
        q = f'identifier:"arXiv:{arxiv}"'
    else:
        return []
    recs, _ = _query(http, token, q, rows=5)
    return recs


def citing(http, token, bibcodes):
    q = " OR ".join(f'citations(bibcode:"{b}")' for b in bibcodes)
    recs, total = _query(http, token, q)
    return recs, total
