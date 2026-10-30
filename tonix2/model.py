"""Common record format that every source (ORCID, INSPIRE, ADS, OpenAlex) is converted to."""
from dataclasses import dataclass, field

# kinds: journal, proceedings, chapter, book, thesis, preprint, erratum, other
PUBLISHED_KINDS = ("journal", "proceedings", "chapter", "book")


@dataclass
class Record:
    source: str                     # orcid | inspire | ads | openalex
    source_id: str                  # put-code, recid, bibcode, W-id
    title: str = ""
    year: int | None = None
    authors: list = field(default_factory=list)
    author_count: int | None = None
    dois: set = field(default_factory=set)      # journal DOIs (never arXiv DOIs)
    arxiv: str | None = None
    link_ids: set = field(default_factory=set)  # extra 'doi:..'/'arxiv:..' keys that mean "same work"
    kind: str = "other"
    journal: str = ""
    volume: str = ""
    pages: str = ""
    issns: set = field(default_factory=set)
    refereed: bool | None = None
    thesis_degree: str = ""
    thesis_school: str = ""
    country_codes: set = field(default_factory=set)
    url: str = ""
    ext: dict = field(default_factory=dict)     # bibcode, eid, pmid, ...

    def keys(self):
        out = {"doi:" + d for d in self.dois}
        if self.arxiv:
            out.add("arxiv:" + self.arxiv)
        return out | set(self.link_ids)


@dataclass
class Merged:
    """One work after merging records from several sources and versions."""
    records: list
    title: str = ""
    year: int | None = None
    authors: list = field(default_factory=list)
    author_count: int | None = None
    doi: str | None = None
    dois: set = field(default_factory=set)
    arxiv: str | None = None
    kind: str = "other"
    journal: str = ""
    volume: str = ""
    pages: str = ""
    issns: set = field(default_factory=set)
    refereed: bool | None = None
    thesis_degree: str = ""
    thesis_school: str = ""
    country_codes: set = field(default_factory=set)

    @property
    def sources(self):
        return sorted({r.source for r in self.records})

    def handles(self, source):
        return sorted({r.source_id for r in self.records if r.source == source})

    def link(self):
        if self.doi:
            return "https://doi.org/" + self.doi
        if self.arxiv:
            return "https://arxiv.org/abs/" + self.arxiv
        for r in self.records:
            if r.url:
                return r.url
        return ""
