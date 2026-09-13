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

_MAX_INDEX_PAGES = 50

def fetch_all_items(lib_id: str, limit: int = 2000) -> list[dict]:
    """Fetch every item of a library, preferring one big page.

    Falls back to offset pagination when the server caps the page size.
    Raises 502 instead of returning a silently truncated list, so the
    catalog index is never built from partial data.
    """
    items: list[dict] = []
    seen_ids: set[str] = set()
    raw_seen = 0
    offset = 0
    total: Optional[int] = None
    for _ in range(_MAX_INDEX_PAGES):
        data = get_json(
            f"/api/libraries/{lib_id}/items",
            params={"limit": limit, "offset": offset, "collapseseries": 0},
            cache_ttl=_settings.INDEX_TTL,
        )
        if total is None and data.get("total") is not None:
            total = int(data["total"])
        page = _extract_list(data)
        if not page:
            break
        raw_seen += len(page)
        new = [it for it in page if it.get("id") and it["id"] not in seen_ids]
        items.extend(new)
        seen_ids.update(it["id"] for it in new)
        if total is not None and raw_seen >= total:
            break
        if not new:
            raise HTTPException(
                status_code=502,
                detail=f"ABS pagination is stuck for library {lib_id} "
                       f"(got {raw_seen} of {total} items)",
            )
        offset += len(page)
    else:
        raise HTTPException(
            status_code=502,
            detail=f"ABS library {lib_id} did not return all items "
                   f"within {_MAX_INDEX_PAGES} pages",
        )
    if total is not None and raw_seen < total:
        raise HTTPException(
            status_code=502,
            detail=f"ABS library {lib_id} returned {raw_seen} of {total} items",
        )
    return items

def search_items(lib_id: str, q: str) -> list[dict]:
    data = get_json(f"/api/libraries/{lib_id}/search", params={"q": q})
    return _extract_list(data)
