"""Polite JSON-over-HTTP client.

* retries on rate limits and server errors, honouring Retry-After
* keeps a minimum gap between calls to the same host
* caches successful answers on disk for 24 h; API keys and tokens are never
  part of the cache file names or contents, and never appear in error messages
"""
import hashlib
import json
import os
import threading
import time
from collections import Counter
from urllib.parse import urlencode, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SECRET_PARAMS = {"api_key", "mailto"}
MIN_INTERVAL = {
    "inspirehep.net": 0.4,          # INSPIRE allows 15 requests / 5 s
    "api.openalex.org": 0.12,
    "api.adsabs.harvard.edu": 0.25,
    "pub.orcid.org": 0.1,
}


class HttpError(Exception):
    pass


class Http:
    def __init__(self, cache_dir, ttl=24 * 3600, contact_email=None):
        self.cache_dir = cache_dir
        self.ttl = ttl
        os.makedirs(cache_dir, exist_ok=True)
        ua = "tonix2/0.1 (Sonix citation helper)"
        if contact_email:
            ua += f" mailto:{contact_email}"
        self.session = requests.Session()
        self.session.headers["User-Agent"] = ua
        retry = Retry(total=4, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET",), respect_retry_after_header=True)
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self._last = {}
        self._lock = threading.Lock()
        self.calls = Counter()
        self.cache_hits = Counter()

    def _throttle(self, host):
        gap = MIN_INTERVAL.get(host, 0.2)
        with self._lock:
            wait = self._last.get(host, 0) + gap - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last[host] = time.monotonic()

    def _cache_path(self, url, params):
        public = sorted((k, str(v)) for k, v in params.items() if k not in SECRET_PARAMS)
        digest = hashlib.sha1((url + "?" + urlencode(public)).encode()).hexdigest()
        return os.path.join(self.cache_dir, digest + ".json")

    def get_json(self, url, params=None, headers=None):
        params = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        host = urlparse(url).netloc
        path = self._cache_path(url, params)
        if self.ttl > 0 and os.path.exists(path) and time.time() - os.path.getmtime(path) < self.ttl:
            try:
                with open(path, encoding="utf-8") as fh:
                    self.cache_hits[host] += 1
                    return json.load(fh)["data"]
            except (OSError, ValueError, KeyError):
                pass

        self._throttle(host)
        self.calls[host] += 1
        h = {"Accept": "application/json"}
        h.update(headers or {})
        try:
            resp = self.session.get(url, params=params, headers=h, timeout=40)
        except requests.exceptions.RetryError:
            raise HttpError(f"{host} kept refusing requests (rate limit or server trouble); try again later") from None
        except requests.RequestException as exc:
            raise HttpError(f"{host} could not be reached ({type(exc).__name__})") from None

        if resp.status_code == 404:
            data = None
        elif resp.status_code in (401, 403):
            raise HttpError(f"{host} refused access (HTTP {resp.status_code}); check the token or key")
        elif resp.status_code >= 400:
            raise HttpError(f"{host} answered HTTP {resp.status_code}")
        else:
            try:
                data = resp.json()
            except ValueError:
                raise HttpError(f"{host} sent a reply that is not JSON") from None
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"data": data}, fh)
        except OSError:
            pass
        return data
