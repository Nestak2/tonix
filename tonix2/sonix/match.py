"""Recognise things that are already in Sonix, and match authors to unit staff."""
import re

from ..fmt import clean_title
from ..ids import ascii_fold, norm_arxiv, norm_doi, norm_title, split_name

# Cyrillic letters that look like Latin ones. Sonix entries sometimes contain
# them by accident (e.g. "Nеw" with a Cyrillic "е"), which breaks plain matching.
_LOOKALIKE = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "к": "k", "м": "m", "т": "t",
    "в": "b", "н": "h", "і": "i", "ј": "j", "А": "A", "Е": "E", "О": "O", "Р": "P", "С": "C", "Т": "T",
    "Х": "X", "К": "K", "М": "M", "В": "B", "Н": "H", "×": "x",
})
_CYR = re.compile(r"[\u0400-\u04ff]")
_LAT = re.compile(r"[A-Za-z]")


def fold_lookalikes(s):
    s = s or ""
    if len(_LAT.findall(s)) >= len(_CYR.findall(s)):
        return s.translate(_LOOKALIKE)
    return s


def match_norm(s):
    return norm_title(fold_lookalikes(s))


_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s,;\"<>]+", re.I)
_ARXIV_RE = re.compile(r"(?<![\d.])(\d{4}\.\d{4,5})(?:v\d+)?(?![\d])")


def ids_in_text(text):
    text = fold_lookalikes(text or "")
    dois = {d for d in (norm_doi(x.rstrip(".)]")) for x in _DOI_RE.findall(text)) if d}
    arx = {a for a in (norm_arxiv(x) for x in _ARXIV_RE.findall(text)) if a}
    return dois, arx


def title_in_text(title, text, threshold=0.85):
    t = match_norm(clean_title(title)).split()
    if len(t) < 3:
        return False
    norm_text = match_norm(text)
    if " ".join(t) in norm_text:
        return True
    words = set(norm_text.split())
    sig = [w for w in t if len(w) >= 4] or t
    if len(sig) < 3:
        return False
    return sum(w in words for w in sig) / len(sig) >= threshold


def same_work(m, text, extra_ids=()):
    """Does the Sonix entry `text` describe the merged work `m`?"""
    dois, arx = ids_in_text(text)
    if dois & set(m.dois) or (m.arxiv and m.arxiv in arx):
        return True
    low = (text or "").lower()
    if any(x and x.lower() in low for x in extra_ids):
        return True
    return title_in_text(m.title, text)


def find_entry(m, entries, extra_ids=()):
    for e in entries:
        if same_work(m, e["text"], extra_ids):
            return e
    return None


# ------------------------------------------------------------ staff names
_BG = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z", "и": "i", "й": "y",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sht", "ъ": "a", "ь": "y", "ю": "yu", "я": "ya",
}


def translit(s):
    out = []
    for c in s or "":
        low = c.lower()
        if low in _BG:
            t = _BG[low]
            out.append(t.capitalize() if c != low else t)
        else:
            out.append(c)
    return "".join(out)


def _loose(s):
    s = re.sub(r"[^a-z]", "", ascii_fold(s).lower())
    for a, b in (("kh", "h"), ("tz", "c"), ("ts", "c"), ("cz", "c"), ("zh", "j"), ("yu", "iu"), ("ya", "ia"),
                 ("w", "v"), ("y", "i")):
        s = s.replace(a, b)
    return s


def author_key(name):
    sur, given = split_name(name)
    return _loose(sur), _loose(given)[:1]


def staff_key(member):
    return _loose(translit(member["surname"])), _loose(translit(member["given"]))[:1]


def match_staff(authors, staff, user_label=None, user_names=()):
    """For each author name return a staff id ('' when not from the unit)."""
    by_key = {}
    for s in sorted(staff, key=lambda s: not s["active"]):       # active people win
        by_key.setdefault(staff_key(s), s["id"])
    user_id = None
    if user_label:
        for s in staff:
            if s["label"].split(")", 1)[-1].strip().startswith(user_label):
                user_id = s["id"]
                break
    user_keys = {author_key(n) for n in user_names if n}
    out = []
    for a in authors:
        k = author_key(a)
        sid = by_key.get(k, "")
        if not sid and user_id and k in user_keys:
            sid = user_id
        out.append(sid)
    return out


def looks_like_preprint(text):
    """Is this Sonix citation entry the arXiv version (arXiv mentioned, no journal DOI)?"""
    low = fold_lookalikes(text or "").lower()
    dois, arx = ids_in_text(text)
    journal_dois = {d for d in dois if not d.startswith("10.48550/")}
    return bool(arx or "arxiv" in low) and not journal_dois


def mentions(text, name):
    n = match_norm(name)
    return bool(n) and len(n) > 3 and n in match_norm(text)


def same_text(a, b):
    a, b = match_norm(a), match_norm(b)
    if not a or not b:
        return False
    return a == b or b[:60] in a or a[:60] in b
