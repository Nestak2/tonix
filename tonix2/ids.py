"""Normalisation of DOIs, arXiv IDs, ORCID iDs, titles and author names."""
import re
import unicodedata

_ARXIV_NEW = re.compile(r"(\d{4}\.\d{4,5})(?:v\d+)?", re.I)
_ARXIV_OLD = re.compile(r"([a-z][a-z\-]*(?:\.[a-z]{2})?/\d{7})(?:v\d+)?", re.I)
_ARXIV_DOI = re.compile(r"^10\.48550/arxiv\.(.+)$", re.I)


def norm_doi(value):
    """Return a lower-case bare DOI ('10.x/y') or None."""
    if not value:
        return None
    s = str(value).strip()
    s = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", s, flags=re.I)
    s = re.sub(r"^doi:\s*", "", s, flags=re.I)
    s = s.strip().rstrip(".").lower()
    return s if s.startswith("10.") and "/" in s else None


def norm_arxiv(value):
    """Return an arXiv identifier without prefix or version, or None."""
    if not value:
        return None
    s = str(value).strip()
    m = _ARXIV_DOI.match(s) or _ARXIV_DOI.match(norm_doi(s) or "")
    if m:
        s = m.group(1)
    s = re.sub(r"^(https?://)?(www\.)?(export\.)?arxiv\.org/(abs|pdf)/", "", s, flags=re.I)
    s = re.sub(r"^arxiv:\s*", "", s, flags=re.I)
    s = re.sub(r"\.pdf$", "", s, flags=re.I)
    m = _ARXIV_NEW.fullmatch(s) or _ARXIV_NEW.match(s)
    if m:
        return m.group(1)
    m = _ARXIV_OLD.fullmatch(s) or _ARXIV_OLD.match(s)
    if m:
        return m.group(1).lower()
    return None


def arxiv_from_doi(doi):
    """'10.48550/arxiv.2101.01234' -> '2101.01234'."""
    m = _ARXIV_DOI.match(doi or "")
    return norm_arxiv(m.group(1)) if m else None


def arxiv_from_url(url):
    if url and "arxiv.org/" in url.lower():
        return norm_arxiv(url)
    return None


def arxiv_doi(arxiv_id):
    return f"10.48550/arxiv.{arxiv_id}" if arxiv_id else None


def split_dois(values):
    """Split DOIs into (journal DOIs, arXiv id or None)."""
    dois, arxiv = set(), None
    for v in values or []:
        d = norm_doi(v)
        if not d:
            continue
        a = arxiv_from_doi(d)
        if a:
            arxiv = arxiv or a
        else:
            dois.add(d)
    return dois, arxiv


# ---------------------------------------------------------------- ORCID
def parse_orcid(value):
    """Accept '0000-0002-1825-0097' or an orcid.org URL. Return the iD or None."""
    if not value:
        return None
    m = re.search(r"(\d{4})-?(\d{4})-?(\d{4})-?(\d{3}[\dXx])", str(value))
    if not m:
        return None
    digits = "".join(m.groups()).upper()
    total = 0
    for ch in digits[:-1]:
        total = (total + int(ch)) * 2
    check = (12 - total % 11) % 11
    expected = "X" if check == 10 else str(check)
    if digits[-1] != expected:
        return None
    return "-".join(digits[i:i + 4] for i in range(0, 16, 4))


# ---------------------------------------------------------------- text
def ascii_fold(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c))


_LATEX_CMD = re.compile(r"\\[a-zA-Z]+\s*")


def norm_title(title):
    s = ascii_fold(title or "").lower()
    s = s.replace("\\ensuremath", "")
    s = _LATEX_CMD.sub(lambda m: m.group(0)[1:].strip() + " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_ROMAN = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"}


def numeric_tokens(normalized_title):
    """Numbers and roman numerals: these distinguish 'Paper I' from 'Paper II'."""
    return {t for t in normalized_title.split() if t.isdigit() or t in _ROMAN}


_ERRATUM = re.compile(r"^\s*(erratum|errata|corrigendum|correction to|publisher'?s note|addendum|retraction)\b", re.I)


def is_erratum_title(title):
    return bool(_ERRATUM.match(ascii_fold(title or "")))


# ---------------------------------------------------------------- names
def split_name(name):
    """Return (surname, given names) for 'Last, First' or 'First Last'."""
    name = re.sub(r"\s+", " ", (name or "").replace("{", "").replace("}", "")).strip()
    if "," in name:
        sur, given = [x.strip() for x in name.split(",", 1)]
        return sur, given
    parts = name.split(" ")
    if len(parts) == 1:
        return parts[0], ""
    return parts[-1], " ".join(parts[:-1])


def name_key(name):
    """('escudero', 'h') style key used to spot shared authors across databases."""
    sur, given = split_name(name)
    sur = re.sub(r"[^a-z ]", "", ascii_fold(sur).lower()).split()
    if not sur:
        return None
    given = re.sub(r"[^a-z]", "", ascii_fold(given).lower())
    return (sur[-1], given[:1])


def norm_issn(value):
    s = re.sub(r"[^0-9Xx]", "", str(value or "")).upper()
    return s if len(s) == 8 else None
