from urllib.parse import quote
from fastapi import APIRouter, Depends, Query, Response
from lxml import etree

from opds_bridge.config import get_settings
from opds_bridge.security.basic import basic_auth_guard
from opds_bridge.services import abs_client as abs
from opds_bridge.opds.atom import atom_root, add_nav_entry, add_search_link, add_search_entry
from opds_bridge.opds.builders import make_book_entry, add_pagination_links

router = APIRouter()

@router.get("/opds", response_class=Response, summary="Root OPDS catalog")
def opds_root(_=Depends(basic_auth_guard), settings=Depends(get_settings)):
    libs = [l for l in abs.list_libraries() if l.get("mediaType") == "book"]
    feed = atom_root("Audiobookshelf OPDS", "/opds", kind="navigation")

    # Add search link and entry
    add_search_link(feed, "/opds/search.xml")
    add_search_entry(feed, "/opds/search.xml")

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
    has_next = len(raw_items) == limit

    for it in raw_items:
        item_id = it.get("id")
        if not item_id:
            continue
        detail = it
        media = (detail.get("media") or {})
        if not media.get("ebookFile"):
            detail = abs.item_details(item_id)
            media = (detail.get("media") or {})
        if media.get("ebookFile") or media.get("ebookFormat"):
            make_book_entry(feed, detail, str(settings.ABS_BASE))

    add_pagination_links(feed, f"/opds/library/{lib_id}", page, limit, has_next)
    xml = etree.tostring(feed, xml_declaration=True, encoding="UTF-8")
    return Response(content=xml, media_type="application/atom+xml;profile=opds-catalog;kind=acquisition")

@router.get("/opds/search.xml", response_class=Response,
            summary="OpenSearch description document")
def opensearch_description(_=Depends(basic_auth_guard)):
    """OpenSearch description for OPDS search"""
    opensearch = etree.Element("OpenSearchDescription",
                               nsmap={None: "http://a9.com/-/spec/opensearch/1.1/"})
    etree.SubElement(opensearch, "ShortName").text = "Audiobookshelf"
    etree.SubElement(opensearch, "Description").text = "Search books in Audiobookshelf"
    etree.SubElement(opensearch, "InputEncoding").text = "UTF-8"
    etree.SubElement(opensearch, "OutputEncoding").text = "UTF-8"

    url = etree.SubElement(opensearch, "Url")
    url.set("type", "application/atom+xml;profile=opds-catalog;kind=acquisition")
    url.set("template", "/opds/search?q={searchTerms}")

    xml = etree.tostring(opensearch, xml_declaration=True, encoding="UTF-8")
    return Response(
        content=xml,
        media_type="application/opensearchdescription+xml",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@router.get("/opds/search", response_class=Response,
            summary="Search across all libraries")
def opds_search(q: str = Query("", description="Search query"),
                _=Depends(basic_auth_guard),
                settings=Depends(get_settings)):
    """Search for books across all libraries"""
    feed = atom_root(f"Search results: {q}", f"/opds/search?q={quote(q)}")

    if not q:
        # Empty search, return empty feed
        xml = etree.tostring(feed, xml_declaration=True, encoding="UTF-8")
        return Response(content=xml, media_type="application/atom+xml;profile=opds-catalog;kind=acquisition")

    # Search in all book libraries
    libs = [l for l in abs.list_libraries() if l.get("mediaType") == "book"]
    all_results = []

    for lib in libs:
        try:
            results = abs.search_items(lib["id"], q)
            all_results.extend(results)
        except Exception:
            # Skip libraries that fail to search
            continue

    # Build entries for found items
    for item in all_results:
        # Search results have structure: {'libraryItem': {...}}
        library_item = item.get("libraryItem", item)
        item_id = library_item.get("id")
        if not item_id:
            continue

        # Use libraryItem as detail since it contains media
        detail = library_item
        media = (detail.get("media") or {})

        # Check if it has ebook file
        if media.get("ebookFile") or media.get("ebookFormat"):
            make_book_entry(feed, detail, str(settings.ABS_BASE))

    xml = etree.tostring(feed, xml_declaration=True, encoding="UTF-8")
    return Response(
        content=xml,
        media_type="application/atom+xml;profile=opds-catalog;kind=acquisition",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )
