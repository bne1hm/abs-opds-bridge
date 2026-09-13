from fastapi import APIRouter, Depends, Query, Request, Response
from lxml import etree

from opds_bridge.api.search import BOOK_SEARCH_TEMPLATE
from opds_bridge.config import get_settings
from opds_bridge.opds.atom import (add_nav_entry, add_search_entry,
                                   add_search_links, atom_root)
from opds_bridge.opds.builders import make_book_entry, add_pagination_links
from opds_bridge.security.basic import basic_auth_guard
from opds_bridge.services import abs_client as abs

router = APIRouter()

# Hide the OpenSearch entry from Moon+ Reader and KOReader; they search via feed-head links.
_NO_SEARCH_ENTRY_UA = ("moon", "koreader")

def _wants_search_entry(user_agent: str) -> bool:
    ua = (user_agent or "").lower()
    return not any(marker in ua for marker in _NO_SEARCH_ENTRY_UA)

@router.get("/opds", response_class=Response, summary="Root OPDS catalog")
def opds_root(request: Request, _=Depends(basic_auth_guard)):
    libs = [l for l in abs.list_libraries() if l.get("mediaType") == "book"]
    feed = atom_root("Audiobookshelf OPDS", "/opds", kind="navigation")

    add_search_links(feed, "/opds/search.xml", BOOK_SEARCH_TEMPLATE, kind="acquisition")
    if _wants_search_entry(request.headers.get("user-agent", "")):
        add_search_entry(feed, "Search", "/opds/search.xml",
                         "Search books, authors and genres")
    add_nav_entry(feed, "Search Authors", "/opds/authors/search",
                  kind="navigation", entry_id="urn:abs:authors")
    add_nav_entry(feed, "Search Genres", "/opds/genres/search",
                  kind="navigation", entry_id="urn:abs:genres")

    for l in libs:
        add_nav_entry(feed, l["name"], f"/opds/library/{l['id']}?page=1")
    xml = etree.tostring(feed, xml_declaration=True, encoding="UTF-8")
    return Response(
        content=xml,
        media_type="application/atom+xml;profile=opds-catalog;kind=navigation",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@router.get("/opds/library/{lib_id}", response_class=Response,
            summary="Books in library (ebooks only)")
def opds_library(lib_id: str,
                 page: int = Query(1, ge=1),
                 limit: int = Query(100, ge=1, le=500),
                 _=Depends(basic_auth_guard),
                 settings=Depends(get_settings)):
    raw_items = abs.fetch_page_items(lib_id, page, limit)
    feed = atom_root(f"Library {lib_id}", f"/opds/library/{lib_id}?page={page}&limit={limit}")
    add_search_links(feed, "/opds/search.xml", BOOK_SEARCH_TEMPLATE, kind="acquisition")
    has_next = len(raw_items) == limit

    for it in raw_items:
        if not it.get("id"):
            continue
        media = (it.get("media") or {})
        if media.get("ebookFile") or media.get("ebookFormat"):
            make_book_entry(feed, it, str(settings.ABS_BASE))

    add_pagination_links(feed, f"/opds/library/{lib_id}", page, limit, has_next)
    xml = etree.tostring(feed, xml_declaration=True, encoding="UTF-8")
    return Response(content=xml, media_type="application/atom+xml;profile=opds-catalog;kind=acquisition")
