"""Run settings and lookup of tokens saved on this computer."""
import os
from dataclasses import dataclass
from pathlib import Path


def _read(path):
    try:
        value = Path(path).expanduser().read_text(encoding="utf-8").strip()
        return value or None
    except OSError:
        return None


def saved_ads_token():
    """ADS convention: $ADS_API_TOKEN, then ~/.ads/token."""
    if os.environ.get("ADS_API_TOKEN"):
        return os.environ["ADS_API_TOKEN"].strip(), "the ADS_API_TOKEN environment variable"
    tok = _read("~/.ads/token")
    return (tok, "~/.ads/token") if tok else (None, None)


def saved_openalex_key():
    if os.environ.get("OPENALEX_API_KEY"):
        return os.environ["OPENALEX_API_KEY"].strip(), "the OPENALEX_API_KEY environment variable"
    key = _read("~/.openalex/key")
    return (key, "~/.openalex/key") if key else (None, None)


@dataclass
class Settings:
    orcid: str
    sonix_email: str = ""
    sonix_password: str = ""          # kept in memory only
    ads_token: str | None = None
    openalex_key: str | None = None
    contact_email: str = ""
    joined_year: int | None = None
    refresh: bool = False
    browser: str = "firefox"          # firefox | chrome
    show_browser: bool = False

    def public(self):
        """Settings that are safe to show or save (no secrets)."""
        return {
            "orcid": self.orcid,
            "sonix_email": self.sonix_email,
            "ads": bool(self.ads_token),
            "openalex_key": bool(self.openalex_key),
            "contact_email": bool(self.contact_email),
            "joined_year": self.joined_year,
            "browser": self.browser,
        }
