"""Choose the Sonix "type of citing publication" (Вид на цитиращото издание)."""
import csv
import glob
import os
import re

from .ids import norm_issn, norm_title

# value attribute of the <select name="citeTypeID"> options in Sonix
TYPE_LABELS = {
    "8": "Scopus/WoS publication",
    "1": "International edition",
    "2": "National edition",
    "3": "Thesis (abroad)",
    "4": "Thesis (Bulgaria)",
    "9": "Preprint in repository",
    "0": "Not set",
}
_BG = re.compile(r"bulgar|sofia|plovdiv|varna|burgas|rousse|ruse\b|българ|софия|пловдив|варна", re.I)
_DOCTORAL = {"phd", "doctoral", "doctorate", "habilitation"}


class Scimago:
    """Optional Scimago Journal Rank CSV (a list of Scopus sources with SJR values).

    Download it from scimagojr.com ("Download data") and put the .csv file in the
    data/ folder. Without it, journal citations are assumed indexed when refereed.
    """

    def __init__(self, folder):
        self.by_issn, self.by_title, self.path = {}, {}, None
        files = sorted(glob.glob(os.path.join(folder, "*.csv")), key=os.path.getmtime, reverse=True)
        for path in files:
            try:
                self._load(path)
                self.path = path
                break
            except (OSError, ValueError, KeyError, csv.Error):
                self.by_issn, self.by_title = {}, {}

    @property
    def loaded(self):
        return bool(self.by_issn)

    def _load(self, path):
        with open(path, encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            if "Issn" not in (reader.fieldnames or []):
                raise ValueError("not a Scimago file")
            for row in reader:
                info = {
                    "title": row.get("Title", ""),
                    "sjr": (row.get("SJR") or "").replace(",", "."),
                    "quartile": row.get("SJR Best Quartile", ""),
                    "type": row.get("Type", ""),
                }
                for part in (row.get("Issn") or "").split(","):
                    issn = norm_issn(part)
                    if issn:
                        self.by_issn[issn] = info
                if info["title"]:
                    self.by_title[norm_title(info["title"])] = info
        if not self.by_issn:
            raise ValueError("empty Scimago file")

    def lookup(self, issns, journal=""):
        for i in issns or ():
            if i in self.by_issn:
                return self.by_issn[i]
        if journal:
            return self.by_title.get(norm_title(journal))
        return None


def cite_type(m, scimago=None):
    """Return (sonix type code, notes, selected by default)."""
    notes = []
    if m.kind == "erratum":
        return "0", ["Erratum or publisher's note, normally not counted as a citation"], False
    if m.kind == "thesis":
        bg = "BG" in m.country_codes or bool(_BG.search(m.thesis_school or ""))
        code = "4" if bg else "3"
        deg = (m.thesis_degree or "").lower()
        if deg and deg not in _DOCTORAL:
            return code, [f"{deg.capitalize()} thesis, not a doctoral dissertation"], False
        if not deg:
            notes.append("Degree unknown: check that it is a doctoral thesis")
        return code, notes, True
    if m.kind == "preprint":
        return "9", notes, True
    if m.kind in ("journal", "proceedings", "chapter", "book"):
        if _BG.search(m.journal or ""):
            notes.append("Bulgarian edition: choose “National edition” if it is not in Scopus/WoS")
        if scimago is not None and scimago.loaded:
            if scimago.lookup(m.issns, m.journal):
                return "8", notes, True
            notes.append("Not in the Scimago (Scopus) list: check indexing")
            return "1", notes, True
        if m.kind == "journal" and m.refereed is not False:
            notes.append("Scopus/WoS indexing assumed, not checked")
            return "8", notes, True
        notes.append("Indexing unknown: check the type")
        return "1", notes, True
    return "0", ["Unrecognised document type (abstract, dataset, software...)"], False
