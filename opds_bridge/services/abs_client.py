from typing import Optional
from urllib.parse import urlencode
import requests
from fastapi import HTTPException
from opds_bridge.config import get_settings
from opds_bridge.services.cache import Cache

_settings = get_settings()
_cache = Cache(default_ttl=_settings.CACHE_TTL_DEFAULT)

def _session() -> requests.Session:
    s = requests.Session()
    s.headers["Accept"] = "application/json"
    if _settings.ABS_TOKEN:
        s.headers["Authorization"] = f"Bearer {_settings.ABS_TOKEN}"
    return s

def _cache_key(url: str, params: Optional[dict]) -> str:
    return f"{url}?{urlencode(params or {})}"

def get_json(path: str, params: Optional[dict] = None, cache_ttl: Optional[int] = None) -> dict:
    base = str(_settings.ABS_BASE).rstrip("/")
    url = f"{base}{path}"
    key = _cache_key(url, params)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    try:
        r = _session().get(url, params=params, timeout=20)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"ABS GET failed: {e}")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"ABS GET {path} -> {r.status_code} {r.text[:200]}")

    data = r.json()
    _cache.set(key, data, ttl=cache_ttl)
    return data

def stream_download(item_id: str, headers: Optional[dict] = None):
    base = str(_settings.ABS_BASE).rstrip("/")
    token = _settings.ABS_TOKEN or ""
    url = f"{base}/api/items/{item_id}/ebook?token={token}"
    try:
        r = _session().get(url, headers=headers or {}, stream=True, timeout=120)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"ABS fetch failed: {e}")
    if r.status_code not in (200, 206):
        body = r.text
        if isinstance(body, str) and len(body) > 200:
            body = body[:200] + "..."
        raise HTTPException(status_code=r.status_code, detail=body)
    return r, r.iter_content(1 << 14)

def list_libraries() -> list[dict]:
    return get_json("/api/libraries").get("libraries", [])

def _extract_list(obj: dict) -> list:
    for k in ("items", "libraryItems", "results"):
        v = obj.get(k)
        if isinstance(v, list) and v:
            return v
    if isinstance(obj.get("book"), list):
        return obj["book"]
    if isinstance(obj.get("book"), dict):
        return [obj["book"]]
    return []

def fetch_page_items(lib_id: str, page: int, limit: int) -> list[dict]:
    base = f"/api/libraries/{lib_id}/items"

    data = get_json(base, params={"page": page, "limit": limit, "collapseseries": 0})
    items = _extract_list(data)
    if items:
        return items

    data = get_json(base, params={"offset": (page - 1) * limit, "limit": limit, "collapseseries": 0})
    items = _extract_list(data)
    if items:
        return items

    data = get_json(base, params={"limit": limit, "collapseseries": 0})
    return _extract_list(data)

def item_details(item_id: str) -> dict:
    return get_json(f"/api/items/{item_id}")

def search_items(lib_id: str, q: str) -> list[dict]:
    data = get_json(f"/api/libraries/{lib_id}/search", params={"q": q})
    return _extract_list(data)
