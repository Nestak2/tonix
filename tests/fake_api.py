"""Offline stand-ins for the four APIs, shaped like their real JSON replies."""
import re
from collections import Counter

ORCID_ID = "0000-0002-1825-0097"


def _ext(t, v, rel="self"):
    return {"external-id-type": t, "external-id-value": v, "external-id-relationship": rel}


def _ws(pc, title, typ, year, ext, journal=None):
    return {"put-code": pc, "title": {"title": {"value": title}}, "type": typ,
            "publication-date": {"year": {"value": str(year)}},
            "journal-title": {"value": journal} if journal else None,
            "external-ids": {"external-id": ext}}


ORCID_RECORD = {
    "person": {"name": {"given-names": {"value": "Elena"}, "family-name": {"value": "Petrova"}},
               "other-names": {"other-name": [{"content": "E. Petrova"}]}},
    "activities-summary": {"works": {"group": [
        # same journal paper from two ORCID sources -> one group, two summaries
        {"work-summary": [
            _ws(1, "A survey of cool dwarfs in the solar neighbourhood", "journal-article", 2021,
                [_ext("doi", "10.1093/mnras/stab001")], "Monthly Notices of the Royal Astronomical Society"),
            _ws(2, "A survey of cool dwarfs in the solar neighbourhood", "journal-article", 2021,
                [_ext("doi", "https://doi.org/10.1093/MNRAS/STAB001")], "MNRAS"),
        ]},
        # its arXiv version, separate group, linked only through INSPIRE/ADS
        {"work-summary": [
            _ws(3, "A survey of cool dwarfs in the Solar neighbourhood", "preprint", 2020,
                [_ext("arxiv", "arXiv:2101.00001")], "arXiv e-prints"),
        ]},
        # medical engineering paper, older, no arXiv
        {"work-summary": [
            _ws(4, "Finite element model of the human knee joint under impact loading", "journal-article", 2015,
                [_ext("doi", "10.1016/j.medengphy.2015.01.002")], "Medical Engineering & Physics"),
        ]},
        # Paper I and Paper II must stay separate
        {"work-summary": [
            _ws(5, "Stellar flares in M dwarfs. I. Detection method", "journal-article", 2022,
                [_ext("doi", "10.1051/0004-6361/202200001")], "Astronomy & Astrophysics"),
        ]},
        {"work-summary": [
            _ws(6, "Stellar flares in M dwarfs. II. Detection method", "journal-article", 2023,
                [_ext("doi", "10.1051/0004-6361/202300002")], "Astronomy & Astrophysics"),
        ]},
        # preprint only
        {"work-summary": [
            _ws(7, "Machine learning photometric redshifts for faint galaxies", "preprint", 2023,
                [_ext("doi", "10.48550/arXiv.2305.12345")]),
        ]},
    ]}},
}

# ------------------------------------------------------------------ INSPIRE
INSPIRE_PAPER = {"id": "2000001", "metadata": {
    "control_number": 2000001,
    "titles": [{"title": "A survey of cool dwarfs in the solar neighbourhood"}],
    "authors": [{"full_name": "Petrova, Elena"}, {"full_name": "Georgiev, Ivan"}],
    "author_count": 2,
    "dois": [{"value": "10.1093/mnras/stab001"}],
    "arxiv_eprints": [{"value": "2101.00001", "categories": ["astro-ph.SR"]}],
    "publication_info": [{"journal_title": "Mon.Not.Roy.Astron.Soc.", "journal_volume": "500", "page_start": "1", "page_end": "20", "year": 2021}],
    "document_type": ["article"], "refereed": True,
}}

INSPIRE_CITING = [
    {"id": "3000001", "metadata": {
        "control_number": 3000001,
        "titles": [{"title": "Redshift evolution of the Hubble constant: Constraints and new insights from an interacting dark energy model"}],
        "authors": [{"full_name": n} for n in ["Dai, Xinyi", "Yang, Yupeng", "Wang, Yicheng", "Qu, Yankun"]],
        "author_count": 4, "dois": [{"value": "10.1103/zg3l-yt32"}],
        "arxiv_eprints": [{"value": "2602.22840"}],
        "publication_info": [{"journal_title": "Phys.Rev.D", "journal_volume": "113", "artid": "063514", "year": 2026}],
        "document_type": ["article"], "refereed": True}},
    {"id": "3000002", "metadata": {
        "control_number": 3000002,
        "titles": [{"title": "{\\ensuremath{\\Lambda}}CDM and Beyond: Neutrinos and the Puzzle of Cosmological Tensions"}],
        "authors": [{"full_name": "Garcia Escudero, Helena"}], "document_type": ["thesis"],
        "thesis_info": {"degree_type": "phd", "institutions": [{"name": "UC, Irvine (main)"}], "date": "2025"}}},
    {"id": "3000003", "metadata": {
        "control_number": 3000003,
        "titles": [{"title": "Flare rates of nearby cool dwarfs"}],
        "authors": [{"full_name": "Petrova, Elena"}, {"full_name": "Smith, John"}],
        "arxiv_eprints": [{"value": "2301.00003"}], "document_type": ["article"], "preprint_date": "2023-01-02"}},
]

# ------------------------------------------------------------------ ADS
ADS_PAPER = {"bibcode": "2021MNRAS.500....1P", "title": ["A survey of cool dwarfs in the solar neighbourhood"],
             "author": ["Petrova, Elena", "Georgiev, Ivan"], "author_count": 2, "year": "2021",
             "doi": ["10.1093/mnras/stab001"], "identifier": ["arXiv:2101.00001", "10.1093/mnras/stab001"],
             "pub": "Monthly Notices of the Royal Astronomical Society", "volume": "500", "page": ["1"],
             "doctype": "article", "property": ["REFEREED"], "issn": ["0035-8711"]}

ADS_CITING = [
    {"bibcode": "2026PhRvD.113f3514D", "title": ["Redshift evolution of the Hubble constant: constraints and new insights from an interacting dark energy model"],
     "author": ["Dai, Xinyi", "Yang, Yupeng", "Wang, Yicheng", "Qu, Yankun"], "author_count": 4, "year": "2026",
     "doi": ["10.1103/zg3l-yt32"], "identifier": ["arXiv:2602.22840"], "pub": "Physical Review D", "volume": "113",
     "page": ["063514"], "doctype": "article", "property": ["REFEREED"], "issn": ["2470-0010"]},
    {"bibcode": "2024AAS...24310203K", "title": ["Cool dwarfs and their flares"], "author": ["Kim, A."], "year": "2024",
     "doctype": "abstract", "pub": "American Astronomical Society Meeting Abstracts", "property": ["NOT REFEREED"]},
    {"bibcode": "2022MNRAS.510..999P", "title": ["Erratum: A survey of cool dwarfs in the solar neighbourhood"],
     "author": ["Petrova, Elena"], "year": "2022", "doi": ["10.1093/mnras/stab999"], "doctype": "erratum",
     "pub": "Monthly Notices of the Royal Astronomical Society", "volume": "510", "property": ["REFEREED"]},
]


# ------------------------------------------------------------------ OpenAlex
def _oa(wid, title, year, typ, doi=None, src=None, src_type="journal", issn=None, authors=(), arxiv_url=None, cc=None):
    locs = [{"landing_page_url": arxiv_url}] if arxiv_url else []
    return {"id": f"https://openalex.org/{wid}", "doi": f"https://doi.org/{doi}" if doi else None,
            "display_name": title, "publication_year": year, "type": typ,
            "primary_location": {"source": {"display_name": src, "type": src_type, "issn": issn or []}} if src else {"source": None},
            "locations": locs,
            "authorships": [{"author": {"display_name": a}, "institutions": [{"display_name": "Sofia University", "country_code": cc}] if cc else []} for a in authors],
            "biblio": {}}


OA_WORKS = {
    "10.1093/mnras/stab001": _oa("W1", "A survey of cool dwarfs in the solar neighbourhood", 2021, "article",
                                 "10.1093/mnras/stab001", "Monthly Notices of the Royal Astronomical Society",
                                 issn=["0035-8711"], authors=["Elena Petrova", "Ivan Georgiev"]),
    "10.48550/arxiv.2101.00001": _oa("W3", "A survey of cool dwarfs in the solar neighbourhood", 2020, "preprint",
                                     "10.48550/arxiv.2101.00001", "arXiv (Cornell University)", "repository",
                                     authors=["Elena Petrova", "Ivan Georgiev"]),
    "10.1016/j.medengphy.2015.01.002": _oa("W2", "Finite element model of the human knee joint under impact loading", 2015,
                                           "article", "10.1016/j.medengphy.2015.01.002", "Medical Engineering & Physics",
                                           issn=["1350-4533"], authors=["Elena Petrova", "Petar Dimitrov", "Anna Koleva"]),
}

OA_CITING = {
    "W1|W3": [
        _oa("W10", "Redshift evolution of the Hubble constant: Constraints and new insights from an interacting dark energy model",
            2026, "article", "10.1103/zg3l-yt32", "Physical Review D", issn=["2470-0010", "2470-0029"],
            authors=["Xinyi Dai", "Yupeng Yang", "Yicheng Wang", "Yankun Qu"]),
        _oa("W11", "Photometric variability of red dwarfs", 2024, "article", "10.1515/baj-2024-0001",
            "Bulgarian Astronomical Journal", issn=["1313-2709"], authors=["Stoyan Ivanov"], cc="BG"),
        _oa("W12", "Flare rates of nearby cool dwarfs", 2023, "preprint", "10.48550/arxiv.2301.00003",
            "arXiv (Cornell University)", "repository", authors=["Elena Petrova", "John Smith"]),
    ],
    "W2": [
        _oa("W20", "Impact biomechanics of the knee: a review", 2019, "review", "10.1016/j.jbiomech.2019.01.001",
            "Journal of Biomechanics", issn=["0021-9290"], authors=["Maria Lopez", "Petar Dimitrov"]),
        _oa("W21", "Modelling of knee ligaments", 2018, "dissertation", None, None,
            authors=["Georgi Nikolov"], cc="BG"),
    ],
}


class FakeHttp:
    """Mimics tonix2.http.Http.get_json for the URLs the sources build."""

    def __init__(self):
        self.calls = Counter()
        self.cache_hits = Counter()
        self.seen = []

    def get_json(self, url, params=None, headers=None):
        params = params or {}
        self.seen.append((url, dict(params), dict(headers or {})))
        if "pub.orcid.org" in url:
            self.calls["pub.orcid.org"] += 1
            return ORCID_RECORD if ORCID_ID in url else None
        if "inspirehep.net" in url:
            self.calls["inspirehep.net"] += 1
            q = params["q"]
            if q in ('doi:"10.1093/mnras/stab001"', "arxiv:2101.00001"):
                hits = [INSPIRE_PAPER]
            elif q == "refersto:recid:2000001":
                hits = INSPIRE_CITING if params["page"] == 1 else []
            else:
                hits = []
            return {"hits": {"total": len(INSPIRE_CITING) if "refersto" in q else len(hits), "hits": hits}}
        if "adsabs" in url:
            self.calls["api.adsabs.harvard.edu"] += 1
            assert headers and headers["Authorization"].startswith("Bearer ")
            q = params["q"]
            if q in ('identifier:"10.1093/mnras/stab001"', 'identifier:"arXiv:2101.00001"'):
                docs = [ADS_PAPER]
            elif q == 'citations(bibcode:"2021MNRAS.500....1P")':
                docs = ADS_CITING if params["start"] == 0 else []
            else:
                docs = []
            return {"response": {"numFound": len(ADS_CITING) if "citations" in q else len(docs), "docs": docs}}
        if "openalex" in url:
            self.calls["api.openalex.org"] += 1
            m = re.search(r"/works/doi:(.+)$", url)
            if m:
                return OA_WORKS.get(m.group(1))
            if params["filter"].startswith("doi:"):
                wanted = params["filter"][4:].split("|")
                return {"meta": {"count": 0}, "results": [OA_WORKS[d] for d in wanted if d in OA_WORKS]}
            flt = params["filter"].removeprefix("cites:")
            key = "|".join(sorted(flt.split("|")))
            results = OA_CITING.get(key, []) if params["cursor"] == "*" else []
            return {"meta": {"count": len(OA_CITING.get(key, [])), "next_cursor": "next" if results else None},
                    "results": results}
        raise AssertionError("unexpected URL " + url)
