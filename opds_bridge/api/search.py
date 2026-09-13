from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Query, Response
from lxml import etree

from opds_bridge.config import get_settings
from opds_bridge.opds.atom import (add_nav_entry, add_search_links,
                                   atom_root, make_opensearch_description)
from opds_bridge.opds.builders import add_pagination_links, make_book_entry
from opds_bridge.security.basic import basic_auth_guard
from opds_bridge.services import abs_client as abs
from opds_bridge.services import search_index

router = APIRouter()

BOOK_SEARCH_TEMPLATE = "/opds/search?q={searchTerms}"
AUTHOR_SEARCH_TEMPLATE = "/opds/authors/search?q={searchTerms}&page=1&limit=100"
GENRE_SEARCH_TEMPLATE = "/opds/genres/search?q={searchTerms}&page=1&limit=100"

_NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}

def _xml_response(feed, kind: str) -> Response:
    xml = etree.tostring(feed, xml_declaration=True, encoding="UTF-8")
    return Response(content=xml, media_type=f"application/atom+xml;profile=opds-catalog;kind={kind}")

@router.get("/opds/search.xml", response_class=Response,
            summary="OpenSearch description for universal search")
def book_search_description(_=Depends(basic_auth_guard)):
    doc = make_opensearch_description(
        "Audiobookshelf",
        "Search books, authors and genres in Audiobookshelf",
        BOOK_SEARCH_TEMPLATE,
        kind="acquisition",
    )
    xml = etree.tostring(doc, xml_declaration=True, encoding="UTF-8")
    return Response(content=xml,
                    media_type="application/opensearchdescription+xml",
                    headers=_NO_CACHE_HEADERS)

def _add_universal_facet_entries(feed, index, q: str):
    """Prepend matching authors and genres to book search results.

    A universal feed keeps readers with a single global search dialog
    (FBReader) useful: a name query surfaces author/genre drill-down
    links alongside matching books.
    """
    def add(buckets, prefix, books_path, id_prefix):
        for b in buckets:
            href = f"{books_path}?{urlencode({'name': b.label})}"
            add_nav_entry(feed, f"{prefix}: {b.label}", href,
                          kind="acquisition",
                          entry_id=f"{id_prefix}:{quote(b.key, safe='')}")

    add(search_index.search_authors(index, q), "Author",
        "/opds/authors/books", "urn:abs:author")
    add(search_index.search_genres(index, q), "Genre",
        "/opds/genres/books", "urn:abs:genre")

@router.get("/opds/search", response_class=Response,
            summary="Universal search: authors, genres and books")
def book_search(q: str = Query("", description="Search query"),
                _=Depends(basic_auth_guard),
                settings=Depends(get_settings)):
    feed = atom_root(f"Search results: {q}", f"/opds/search?q={quote(q)}")
    add_search_links(feed, "/opds/search.xml", BOOK_SEARCH_TEMPLATE, kind="acquisition")

    if q:
        try:
            _add_universal_facet_entries(feed, search_index.get_catalog_index(), q)
        except Exception:
            # Facet search is best-effort; book search must still work
            # when the catalog index cannot be built.
            pass

        for lib in [l for l in abs.list_libraries() if l.get("mediaType") == "book"]:
            try:
                results = abs.search_items(lib["id"], q)
            except Exception:
                continue
            for item in results:
                library_item = item.get("libraryItem", item)
                if not library_item.get("id"):
                    continue
                media = (library_item.get("media") or {})
                if media.get("ebookFile") or media.get("ebookFormat"):
                    make_book_entry(feed, library_item, str(settings.ABS_BASE))

    return _xml_response(feed, "acquisition")

def _facet_feed(title: str, search_path: str, self_params: dict,
                description_href: str, template: str, buckets,
                books_path: str, id_prefix: str):
    feed = atom_root(title, f"{search_path}?{urlencode(self_params)}", kind="navigation")
    add_search_links(feed, description_href, template, kind="navigation")
    for b in buckets:
        href = f"{books_path}?{urlencode({'name': b.label})}"
        add_nav_entry(feed, b.label, href, kind="acquisition",
                      entry_id=f"{id_prefix}:{quote(b.key, safe='')}")
    return feed

def _facet_books_feed(title: str, books_path: str, books, page: int, limit: int,
                      has_next: bool, name_param: str, description_href: str,
                      template: str, abs_base: str):
    self_href = f"{books_path}?{urlencode({'name': name_param, 'page': page, 'limit': limit})}"
    feed = atom_root(title, self_href, kind="acquisition")
    add_search_links(feed, description_href, template, kind="navigation")
    for it in books:
        make_book_entry(feed, it, abs_base)
    add_pagination_links(feed, books_path, page, limit, has_next,
                         params={"name": name_param})
    return feed

@router.get("/opds/authors/search.xml", response_class=Response,
            summary="OpenSearch description for author search")
def author_search_description(_=Depends(basic_auth_guard)):
    doc = make_opensearch_description(
        "Search Authors",
        "Search authors in Audiobookshelf",
        AUTHOR_SEARCH_TEMPLATE,
        kind="navigation",
    )
    xml = etree.tostring(doc, xml_declaration=True, encoding="UTF-8")
    return Response(content=xml,
                    media_type="application/opensearchdescription+xml",
                    headers=_NO_CACHE_HEADERS)

@router.get("/opds/authors/search", response_class=Response,
            summary="Browse or search authors")
def author_search(q: str = Query("", description="Author name filter"),
                  page: int = Query(1, ge=1),
                  limit: int = Query(100, ge=1, le=500),
                  _=Depends(basic_auth_guard)):
    index = search_index.get_catalog_index()
    buckets = search_index.search_authors(index, q)
    start = (page - 1) * limit
    window = buckets[start:start + limit]
    has_next = start + limit < len(buckets)
    title = f"Authors: {q}" if q else "Authors"
    feed = _facet_feed(title, "/opds/authors/search",
                       {"q": q, "page": page, "limit": limit},
                       "/opds/authors/search.xml", AUTHOR_SEARCH_TEMPLATE,
                       window, "/opds/authors/books", "urn:abs:author")
    add_pagination_links(feed, "/opds/authors/search", page, limit, has_next,
                         kind="navigation", params={"q": q} if q else None)
    return _xml_response(feed, "navigation")

@router.get("/opds/authors/books", response_class=Response,
            summary="Ebooks by author")
def author_books(name: str = Query(..., description="Author name"),
                 page: int = Query(1, ge=1),
                 limit: int = Query(100, ge=1, le=500),
                 _=Depends(basic_auth_guard),
                 settings=Depends(get_settings)):
    index = search_index.get_catalog_index()
    books = search_index.books_by_author(index, name)
    start = (page - 1) * limit
    window = books[start:start + limit]
    has_next = start + limit < len(books)
    feed = _facet_books_feed(f"Author: {name}", "/opds/authors/books", window,
                             page, limit, has_next, name,
                             "/opds/authors/search.xml", AUTHOR_SEARCH_TEMPLATE,
                             str(settings.ABS_BASE))
    return _xml_response(feed, "acquisition")

@router.get("/opds/genres/search.xml", response_class=Response,
            summary="OpenSearch description for genre search")
def genre_search_description(_=Depends(basic_auth_guard)):
    doc = make_opensearch_description(
        "Search Genres",
        "Search genres in Audiobookshelf",
        GENRE_SEARCH_TEMPLATE,
        kind="navigation",
    )
    xml = etree.tostring(doc, xml_declaration=True, encoding="UTF-8")
    return Response(content=xml,
                    media_type="application/opensearchdescription+xml",
                    headers=_NO_CACHE_HEADERS)

@router.get("/opds/genres/search", response_class=Response,
            summary="Browse or search genres")
def genre_search(q: str = Query("", description="Genre name filter"),
                 page: int = Query(1, ge=1),
                 limit: int = Query(100, ge=1, le=500),
                 _=Depends(basic_auth_guard)):
    index = search_index.get_catalog_index()
    buckets = search_index.search_genres(index, q)
    start = (page - 1) * limit
    window = buckets[start:start + limit]
    has_next = start + limit < len(buckets)
    title = f"Genres: {q}" if q else "Genres"
    feed = _facet_feed(title, "/opds/genres/search",
                       {"q": q, "page": page, "limit": limit},
                       "/opds/genres/search.xml", GENRE_SEARCH_TEMPLATE,
                       window, "/opds/genres/books", "urn:abs:genre")
    add_pagination_links(feed, "/opds/genres/search", page, limit, has_next,
                         kind="navigation", params={"q": q} if q else None)
    return _xml_response(feed, "navigation")

@router.get("/opds/genres/books", response_class=Response,
            summary="Ebooks by genre")
def genre_books(name: str = Query(..., description="Genre name"),
                page: int = Query(1, ge=1),
                limit: int = Query(100, ge=1, le=500),
                _=Depends(basic_auth_guard),
                settings=Depends(get_settings)):
    index = search_index.get_catalog_index()
    books = search_index.books_by_genre(index, name)
    start = (page - 1) * limit
    window = books[start:start + limit]
    has_next = start + limit < len(books)
    feed = _facet_books_feed(f"Genre: {name}", "/opds/genres/books", window,
                             page, limit, has_next, name,
                             "/opds/genres/search.xml", GENRE_SEARCH_TEMPLATE,
                             str(settings.ABS_BASE))
    return _xml_response(feed, "acquisition")
