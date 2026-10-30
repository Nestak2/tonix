"""Citation text in the style of 'Elsevier - Vancouver (et al. for 3+ authors)'.

Same layout as the CSL file used by the original tonix.rb, for example:
Dai X, Yang Y, Wang Y, et al. Title. Phys Rev D 2026;113:063514. https://doi.org/10.1103/zg3l-yt32.
"""
import re

from .ids import split_name

_GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "zeta": "ζ", "eta": "η",
    "theta": "θ", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ",
    "sigma": "σ", "tau": "τ", "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ",
    "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω", "odot": "⊙", "sim": "~", "times": "×", "pm": "±",
}


def clean_title(title):
    s = (title or "").replace("\\ensuremath", "")
    s = re.sub(r"\\([A-Za-z]+)", lambda m: _GREEK.get(m.group(1), m.group(1)), s)
    s = re.sub(r"<[^>]+>", "", s)                 # <i>, <sub> from Crossref/OpenAlex
    s = s.replace("{", "").replace("}", "").replace("$", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s.rstrip(".")


def _initials(given):
    parts = re.split(r"[\s\-.]+", given or "")
    return "".join(p[0].upper() for p in parts if p and p[0].isalpha())


def vancouver_name(name):
    if "collaboration" in (name or "").lower() or "team" in (name or "").lower().split():
        return name.strip()
    sur, given = split_name(name)
    ini = _initials(given)
    return f"{sur} {ini}".strip()


def authors_text(authors, count=None):
    if not authors:
        return ""
    total = max(count or 0, len(authors))
    shown = [vancouver_name(a) for a in authors[: (3 if total > 3 else total)]]
    text = ", ".join(n for n in shown if n)
    return text + (", et al" if total > 3 else "")


def short_journal(name):
    s = re.sub(r"\.\s*", " ", name or "")
    return re.sub(r"\s+", " ", s).strip()


_DEGREE = {"phd": "PhD thesis", "doctoral": "PhD thesis", "habilitation": "Habilitation thesis",
           "master": "Master's thesis", "bachelor": "Bachelor's thesis", "diploma": "Diploma thesis"}


def citation_text(m):
    head = authors_text(m.authors, m.author_count)
    title = clean_title(m.title)
    year = str(m.year) if m.year else ""
    if m.kind == "thesis":
        tail = ", ".join(x for x in (m.thesis_school, year) if x)
        body = ". ".join(x for x in (title, _DEGREE.get(m.thesis_degree, "Thesis"), tail) if x)
    elif m.kind == "preprint":
        where = f"arXiv:{m.arxiv}" if m.arxiv else ""
        body = ". ".join(x for x in (title, "; ".join(y for y in (where, year) if y)) if x)
    else:
        left = ". ".join(x for x in (title, short_journal(m.journal)) if x)
        yv = ";".join(x for x in (year, m.volume) if x)
        body = " ".join(x for x in (left, yv) if x)
        if m.pages:
            body += ":" + m.pages
    text = f"{head}. {body}" if head else body
    if m.doi:
        text += f". https://doi.org/{m.doi}"
    return text + "."


# ---------------------------------------------------------------- Sonix (MLA-like)
_THESIS = {"phd": "PhD thesis", "doctoral": "PhD thesis", "habilitation": "Habilitation thesis",
           "master": "Master's thesis", "bachelor": "Bachelor's thesis", "diploma": "Diploma thesis"}


def mla_name(name):
    """'Xinyi Dai' or 'Dai, Xinyi' -> 'Dai, X.'"""
    if "collaboration" in (name or "").lower():
        return name.strip()
    sur, given = split_name(name)
    parts = [p for p in re.split(r"[\s.]+", given) if p]
    ini = " ".join("-".join(x[0].upper() + "." for x in p.split("-") if x) for p in parts)
    return f"{sur}, {ini}" if ini else sur


def mla_authors(authors, count=None):
    if not authors:
        return ""
    total = max(count or 0, len(authors))
    shown = [mla_name(a) for a in authors[:3]]
    text = ", ".join(n for n in shown if n)
    return text + (", et al." if total > 3 else "")


def sonix_citation_text(m):
    """The format Sonix asks for on its citation form:
    FamilyName, FirstNameInitial. "Title". Venue, Year
    The DOI goes into Sonix's separate link field, not into this text."""
    authors = mla_authors(m.authors, m.author_count)
    title = clean_title(m.title)
    year = str(m.year) if m.year else ""
    if m.kind == "thesis":
        venue = ", ".join(x for x in (_THESIS.get(m.thesis_degree, "Thesis"), m.thesis_school, year) if x)
    elif m.kind == "preprint":
        venue = ", ".join(x for x in (f"arXiv:{m.arxiv}" if m.arxiv else "arXiv preprint", year) if x)
    else:
        venue = ", ".join(x for x in (m.journal, m.volume, m.pages, year) if x)
    head = authors if authors.endswith(".") else (authors + "." if authors else "")
    quoted = f'"{title}"' if title else ""
    parts = [x for x in (head, quoted + "." if quoted else "", venue) if x]
    return " ".join(parts)
