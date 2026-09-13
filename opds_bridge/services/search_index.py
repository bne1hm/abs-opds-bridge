import re
import threading
from dataclasses import dataclass
from typing import Iterable, Optional

from opds_bridge.config import get_settings
from opds_bridge.services import abs_client
from opds_bridge.services.cache import Cache

_whitespace_re = re.compile(r"\s+")

_INDEX_CACHE_KEY = "ebook-catalog-index"

@dataclass(frozen=True)
class FacetBucket:
    key: str
    label: str
    item_ids: tuple[str, ...]

@dataclass(frozen=True)
class CatalogIndex:
    items_by_id: dict[str, dict]
    authors: tuple[FacetBucket, ...]
    genres: tuple[FacetBucket, ...]

def clean_facet(value: str) -> str:
    return _whitespace_re.sub(" ", value).strip()

def normalize_facet(value: str) -> str:
    return clean_facet(value).casefold()

def split_authors(author_name: str) -> list[str]:
    parts = []
    for chunk in (author_name or "").split(","):
        cleaned = clean_facet(chunk)
        if cleaned:
            parts.append(cleaned)
    return parts

def _is_ebook(item: dict) -> bool:
    media = item.get("media") or {}
    return bool(media.get("ebookFormat") or media.get("ebookFile"))

def build_catalog_index(items_by_library: Iterable[list[dict]]) -> CatalogIndex:
    items_by_id: dict[str, dict] = {}
    author_ids: dict[str, set[str]] = {}
    author_labels: dict[str, str] = {}
    genre_ids: dict[str, set[str]] = {}
    genre_labels: dict[str, str] = {}

    for items in items_by_library:
        for item in items:
            item_id = item.get("id")
            if not item_id or not _is_ebook(item):
                continue
            if item_id in items_by_id:
                continue
            items_by_id[item_id] = item
            metadata = (item.get("media") or {}).get("metadata") or {}

            for author in split_authors(metadata.get("authorName") or ""):
                key = normalize_facet(author)
                if not key:
                    continue
                author_labels.setdefault(key, author)
                author_ids.setdefault(key, set()).add(item_id)

            for genre in metadata.get("genres") or []:
                if not isinstance(genre, str):
                    continue
                label = clean_facet(genre)
                if not label:
                    continue
                key = normalize_facet(label)
                genre_labels.setdefault(key, label)
                genre_ids.setdefault(key, set()).add(item_id)

    def buckets(ids: dict[str, set[str]], labels: dict[str, str]) -> tuple[FacetBucket, ...]:
        return tuple(
            FacetBucket(key=key, label=labels[key], item_ids=tuple(sorted(ids[key])))
            for key in sorted(labels, key=lambda k: labels[k].casefold())
        )

    return CatalogIndex(
        items_by_id=items_by_id,
        authors=buckets(author_ids, author_labels),
        genres=buckets(genre_ids, genre_labels),
    )

_index_cache = Cache(default_ttl=get_settings().INDEX_TTL, maxsize=4)
_build_lock = threading.Lock()

def get_catalog_index() -> CatalogIndex:
    cached = _index_cache.get(_INDEX_CACHE_KEY)
    if cached is not None:
        return cached
    with _build_lock:
        cached = _index_cache.get(_INDEX_CACHE_KEY)
        if cached is not None:
            return cached
        libs = [l for l in abs_client.list_libraries() if l.get("mediaType") == "book"]
        items_by_library = [abs_client.fetch_all_items(l["id"]) for l in libs]
        index = build_catalog_index(items_by_library)
        _index_cache.set(_INDEX_CACHE_KEY, index, ttl=get_settings().INDEX_TTL)
        return index

def _find_bucket(buckets: tuple[FacetBucket, ...], name: str) -> Optional[FacetBucket]:
    key = normalize_facet(name)
    for bucket in buckets:
        if bucket.key == key:
            return bucket
    return None

def search_authors(index: CatalogIndex, query: str) -> list[FacetBucket]:
    needle = normalize_facet(query)
    if not needle:
        return list(index.authors)
    return [b for b in index.authors if needle in b.key]

def search_genres(index: CatalogIndex, query: str) -> list[FacetBucket]:
    needle = normalize_facet(query)
    if not needle:
        return list(index.genres)
    return [b for b in index.genres if needle in b.key]

def _books_in_bucket(index: CatalogIndex, buckets: tuple[FacetBucket, ...], name: str) -> list[dict]:
    bucket = _find_bucket(buckets, name)
    if bucket is None:
        return []
    books = [index.items_by_id[i] for i in bucket.item_ids if i in index.items_by_id]
    books.sort(key=lambda it: (((it.get("media") or {}).get("metadata") or {}).get("title") or "").casefold())
    return books

def books_by_author(index: CatalogIndex, name: str) -> list[dict]:
    return _books_in_bucket(index, index.authors, name)

def books_by_genre(index: CatalogIndex, name: str) -> list[dict]:
    return _books_in_bucket(index, index.genres, name)
