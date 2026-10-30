"""ORCID public API (no login needed): the researcher's name and list of works."""
from ..ids import arxiv_from_doi, is_erratum_title, norm_arxiv, norm_doi, norm_issn
from ..model import Record

BASE = "https://pub.orcid.org/v3.0"

_TYPE_KIND = {
    "journal-article": "journal", "review": "journal", "letter": "journal", "journal-issue": "journal",
    "conference-paper": "proceedings", "conference-proceedings": "proceedings",
    "book-chapter": "chapter", "book": "book", "edited-book": "book",
    "dissertation-thesis": "thesis", "dissertation": "thesis",
    "preprint": "preprint", "working-paper": "preprint", "report": "other",
}


def _val(d, *path):
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


class Person:
    def __init__(self, given="", family="", other=()):
        self.given = given or ""
        self.family = family or ""
        self.other = [o for o in other if o]

    @property
    def display(self):
        return " ".join(x for x in (self.given, self.family) if x) or "(name hidden in ORCID)"

    def name_variants(self):
        out = []
        if self.family:
            out.append(f"{self.family}, {self.given}")
        out.extend(self.other)
        return out


def parse_summary(ws):
    title = _val(ws, "title", "title", "value") or ""
    rec = Record(source="orcid", source_id=str(ws.get("put-code", "")), title=title)
    year = _val(ws, "publication-date", "year", "value")
    rec.year = int(year) if year and str(year).isdigit() else None
    rec.journal = _val(ws, "journal-title", "value") or ""
    rec.url = _val(ws, "url", "value") or ""
    otype = ws.get("type") or ""

    for ext in _val(ws, "external-ids", "external-id") or []:
        etype = (ext.get("external-id-type") or "").lower()
        value = ext.get("external-id-value") or _val(ext, "external-id-normalized", "value")
        rel = (ext.get("external-id-relationship") or "self").lower()
        if etype == "issn":
            issn = norm_issn(value)
            if issn:
                rec.issns.add(issn)
            continue
        if rel == "part-of":
            continue
        if etype == "doi":
            d = norm_doi(value)
            if not d:
                continue
            a = arxiv_from_doi(d)
            if rel == "self":
                if a:
                    rec.arxiv = rec.arxiv or a
                else:
                    rec.dois.add(d)
            else:  # version-of: another version of the same work
                rec.link_ids.add("arxiv:" + a if a else "doi:" + d)
        elif etype == "arxiv":
            a = norm_arxiv(value)
            if a:
                if rel == "self":
                    rec.arxiv = rec.arxiv or a
                else:
                    rec.link_ids.add("arxiv:" + a)
        elif etype in ("bibcode", "eid", "pmid", "wosuid"):
            rec.ext[etype] = value

    kind = _TYPE_KIND.get(otype, "other")
    journal_is_arxiv = "arxiv" in rec.journal.lower()
    if not rec.dois and rec.arxiv and (kind in ("journal", "other", "preprint") or journal_is_arxiv):
        kind = "preprint"
    elif kind == "other" and rec.dois and rec.journal and not journal_is_arxiv:
        kind = "journal"
    if is_erratum_title(title):
        kind = "erratum"
    rec.kind = kind
    if journal_is_arxiv:
        rec.journal = ""
    return rec


def fetch_record(http, orcid_id):
    data = http.get_json(f"{BASE}/{orcid_id}/record")
    if data is None:
        raise LookupError(f"ORCID iD {orcid_id} was not found")
    name = _val(data, "person", "name") or {}
    others = [_val(o, "content") for o in (_val(data, "person", "other-names", "other-name") or [])]
    person = Person(_val(name, "given-names", "value"), _val(name, "family-name", "value"), others)
    records = []
    for group in _val(data, "activities-summary", "works", "group") or []:
        for ws in group.get("work-summary") or []:
            records.append(parse_summary(ws))
    return person, records
