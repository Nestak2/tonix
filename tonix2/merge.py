"""Group records that describe the same work and pick the best metadata.

Two records are the same work when
  * they share a DOI, an arXiv ID or an explicit link (strong link), or
  * their titles are almost identical, the years are close, the first authors
    agree and nothing contradicts it (weak link). A weak link is refused when
    it would join two different journal DOIs or two different arXiv IDs, so a
    conference paper and a later journal paper with the same title stay apart
    as long as both have DOIs.
"""
from collections import Counter, defaultdict
from difflib import SequenceMatcher

from .ids import name_key, norm_title, numeric_tokens
from .model import Merged, PUBLISHED_KINDS

TITLE_RATIO = 0.92
KIND_RANK = {"journal": 0, "proceedings": 1, "chapter": 2, "book": 3,
             "thesis": 4, "preprint": 5, "other": 6, "erratum": 7}
SOURCE_PREF = {"ads": 0, "openalex": 1, "inspire": 2, "orcid": 3}
_STOP = {"with", "from", "into", "using", "their", "between", "about", "through", "under", "over"}


def _tokens(nt):
    return {t for t in nt.split() if len(t) >= 4 and t not in _STOP}


def titles_match(na, nb):
    if not na or not nb:
        return False
    wa, wb = na.split(), nb.split()
    if min(len(wa), len(wb)) < 4:
        return na == nb
    if numeric_tokens(na) != numeric_tokens(nb):
        return False
    return SequenceMatcher(None, na, nb).ratio() >= TITLE_RATIO


def records_compatible(a, b):
    if "erratum" in (a.kind, b.kind):
        return False
    if (a.kind == "thesis") != (b.kind == "thesis"):
        return False
    if a.year and b.year and abs(a.year - b.year) > 2:
        return False
    if a.authors and b.authors:
        ka, kb = name_key(a.authors[0]), name_key(b.authors[0])
        if ka and kb and ka[0] != kb[0]:
            return False
    return True


def cluster(records):
    """Return a list of clusters (lists of records)."""
    n = len(records)
    parent = list(range(n))
    meta = [{"dois": set(r.dois), "arxiv": {r.arxiv} if r.arxiv else set()} for r in records]

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j, check):
        ri, rj = find(i), find(j)
        if ri == rj:
            return
        mi, mj = meta[ri], meta[rj]
        if check:
            if mi["dois"] and mj["dois"] and mi["dois"].isdisjoint(mj["dois"]):
                return
            if mi["arxiv"] and mj["arxiv"] and mi["arxiv"].isdisjoint(mj["arxiv"]):
                return
        parent[rj] = ri
        mi["dois"] |= mj["dois"]
        mi["arxiv"] |= mj["arxiv"]

    # strong links
    first_with_key = {}
    for i, r in enumerate(records):
        for k in r.keys():
            if k in first_with_key:
                union(first_with_key[k], i, check=False)
            else:
                first_with_key[k] = i

    # weak links by title
    norms = [norm_title(r.title) for r in records]
    toks = [_tokens(t) for t in norms]
    index = defaultdict(list)
    for i, ts in enumerate(toks):
        for t in ts:
            index[t].append(i)
    for i in range(n):
        if not toks[i]:
            continue
        counts = Counter(j for t in toks[i] for j in index[t] if j > i)
        need = min(2, len(toks[i]))
        for j, c in counts.items():
            if c < need or find(i) == find(j):
                continue
            if titles_match(norms[i], norms[j]) and records_compatible(records[i], records[j]):
                union(i, j, check=True)

    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(records[i])
    return list(groups.values())


def summarize(records):
    """Build one Merged work out of a cluster, preferring the published version."""
    ordered = sorted(records, key=lambda r: (KIND_RANK.get(r.kind, 9), SOURCE_PREF.get(r.source, 9)))
    best = ordered[0]
    m = Merged(records=list(records))
    m.kind = best.kind
    m.title = next((r.title for r in ordered if r.title), "")

    same_kind = [r for r in ordered if r.kind == best.kind]
    years = [r.year for r in same_kind if r.year] or [r.year for r in records if r.year]
    m.year = years[0] if best.kind in PUBLISHED_KINDS and years else (min(years) if years else None)

    with_authors = [r for r in records if r.authors and r.source != "orcid"] or [r for r in records if r.authors]
    if with_authors:
        top = max(with_authors, key=lambda r: (len(r.authors), -SOURCE_PREF.get(r.source, 9)))
        m.authors = list(top.authors)
    counts = [r.author_count or len(r.authors) for r in records]
    m.author_count = max(counts) if any(counts) else None

    for r in records:
        m.dois |= r.dois
        m.issns |= r.issns
        m.country_codes |= r.country_codes
    m.doi = next((sorted(r.dois)[0] for r in same_kind if r.dois), None) or (sorted(m.dois)[0] if m.dois else None)
    m.arxiv = next((r.arxiv for r in ordered if r.arxiv), None)

    for attr in ("journal", "volume", "pages"):
        val = next((getattr(r, attr) for r in same_kind if getattr(r, attr)), "")
        setattr(m, attr, val)
    if any(r.refereed for r in records):
        m.refereed = True
    theses = [r for r in records if r.kind == "thesis"]
    m.thesis_degree = next((r.thesis_degree for r in theses if r.thesis_degree), "")
    m.thesis_school = next((r.thesis_school for r in theses if r.thesis_school), "")
    return m


def dedupe_records(records):
    seen, out = set(), []
    for r in records:
        key = (r.source, r.source_id)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out
