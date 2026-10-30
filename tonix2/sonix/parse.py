"""Read data out of Sonix HTML pages (structure of Sonix ver. 3.2)."""
import html as htmllib
import re

_TAG = re.compile(r"<[^>]+>")


def text_of(fragment):
    s = _TAG.sub(" ", fragment or "")
    s = htmllib.unescape(s).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def _table_rows(page):
    m = re.search(r'<table id="tblsort".*?<tbody>(.*?)</tbody>', page or "", re.S)
    if not m:
        return []
    return re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S)


def _cells(row):
    return re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)


def has_table(page):
    return '<table id="tblsort"' in (page or "")


def parse_publications(page):
    """Rows of 'Научни публикации и цитирания'."""
    out = []
    for row in _table_rows(page):
        m = re.search(r"/258/(\d+)/staff/publication", row)
        cells = _cells(row)
        if not m or len(cells) < 5:
            continue
        n = re.search(r"(\d+)", text_of(cells[4]))
        year = text_of(cells[3])
        out.append({
            "id": m.group(1),
            "text": text_of(cells[1]),
            "not_in_report": bool(text_of(cells[2])),
            "year": int(year) if year.isdigit() else None,
            "cites": int(n.group(1)) if n else 0,
        })
    return out


def parse_cites(page):
    """Rows of the 'Цитирания' list of one publication."""
    out = []
    for row in _table_rows(page):
        m = re.search(r"/264/(\d+)/(\d+)/\d+/staff/cite", row)
        cells = _cells(row)
        if not m or len(cells) < 4:
            continue
        year = text_of(cells[3])
        out.append({"id": m.group(2), "pub_id": m.group(1), "text": text_of(cells[1]),
                    "not_in_report": bool(text_of(cells[2])), "year": int(year) if year.isdigit() else None})
    return out


_STAFF = re.compile(r"\(\s*([^)]*?)\s*\)\s*(.*?)\s*\((Активен|Неактивен)\)\s*$")


def parse_staff(page):
    """Options of 'Авторът е от звеното' on the new publication form."""
    m = re.search(r'<select[^>]*name="userIDs\[\]".*?</select>', page or "", re.S)
    if not m:
        return []
    out = []
    for value, label in re.findall(r'<option value="(\d+)"[^>]*>(.*?)</option>', m.group(0), re.S):
        label = text_of(label)
        sm = _STAFF.match(label)
        if not sm or value == "0":
            continue
        code, name, active = sm.groups()
        sur, _, given = name.partition(",")
        out.append({"id": value, "code": code, "surname": sur.strip(), "given": given.strip(),
                    "active": active == "Активен", "label": label})
    return out


def parse_current_user(page):
    m = re.search(r'myProfile"[^>]*>(.*?)</a>', page or "", re.S)
    if not m:
        return None
    return text_of(m.group(1)).split("•")[0].strip() or None


def is_logged_in(page):
    return "session/logoff" in (page or "")


def is_login_page(page):
    return 'name="pass"' in (page or "") and not is_logged_in(page)
