import unittest
from unittest import mock
from urllib.parse import parse_qs, urlparse

from lxml import etree

from opds_bridge.api import router as api_router
from opds_bridge.api import search as api_search
from opds_bridge.services.search_index import build_catalog_index

ATOM_NS = "http://www.w3.org/2005/Atom"


def _item(item_id, title, author_name=None, genres=None):
    metadata = {"title": title}
    if author_name is not None:
        metadata["authorName"] = author_name
    if genres is not None:
        metadata["genres"] = genres
    return {"id": item_id, "media": {"metadata": metadata, "ebookFormat": "epub"}}


def _fake_index():
    return build_catalog_index([[
        _item("i1", "Alpha", author_name="Иванов, Петров", genres=["Фантастика"]),
        _item("i2", "Beta", author_name="Иванов", genres=["Фантастика"]),
    ]])


def _parse_links(xml_body):
    root = etree.fromstring(xml_body)
    links = []
    for link in root.findall(f"{{{ATOM_NS}}}link"):
        links.append(dict(link.attrib))
    return root, links


class RootFeedTest(unittest.TestCase):
    @mock.patch.object(api_router.abs, "list_libraries")
    def _root(self, ua, list_libraries):
        list_libraries.return_value = [
            {"id": "lib1", "mediaType": "book", "name": "Fiction"},
            {"id": "lib2", "mediaType": "book", "name": "Tech"},
            {"id": "lib3", "mediaType": "audiobook", "name": "Audio"},
        ]
        request = mock.Mock()
        request.headers = {"user-agent": ua}
        return api_router.opds_root(request=request, _=None)

    @mock.patch.object(api_router.abs, "list_libraries")
    def test_root_menu_order_and_search_links(self, list_libraries):
        list_libraries.return_value = [
            {"id": "lib1", "mediaType": "book", "name": "Fiction"},
            {"id": "lib3", "mediaType": "audiobook", "name": "Audio"},
        ]
        request = mock.Mock()
        request.headers = {"user-agent": "FBReader/3.2"}
        response = api_router.opds_root(request=request, _=None)
        root, links = _parse_links(response.body)

        search_links = [l for l in links if l.get("rel") == "search"]
        self.assertEqual(search_links[0]["type"], "application/opensearchdescription+xml")
        self.assertEqual(search_links[0]["href"], "/opds/search.xml")
        self.assertEqual(search_links[1]["type"],
                         "application/atom+xml;profile=opds-catalog;kind=acquisition")
        self.assertIn("{searchTerms}", search_links[1]["href"])

        titles = [e.text for e in root.findall(f"{{{ATOM_NS}}}entry/{{{ATOM_NS}}}title")]
        self.assertEqual(titles, ["Search", "Search Authors", "Search Genres", "Fiction"])

    @mock.patch.object(api_router.abs, "list_libraries")
    def test_root_is_navigation_feed(self, list_libraries):
        list_libraries.return_value = []
        request = mock.Mock()
        request.headers = {"user-agent": ""}
        response = api_router.opds_root(request=request, _=None)
        self.assertIn("kind=navigation", response.media_type)

    def test_search_entry_hidden_for_moon_and_koreader(self):
        for ua in ("Moon+Reader/8.2", "KOReader/2025.03"):
            response = self._root(ua)
            root, _ = _parse_links(response.body)
            titles = [e.text for e in root.findall(f"{{{ATOM_NS}}}entry/{{{ATOM_NS}}}title")]
            self.assertNotIn("Search", titles, ua)
            self.assertIn("Search Authors", titles, ua)

    def test_search_entry_visible_for_fbreader_and_unknown(self):
        for ua in ("FBReader/3.2", "SomeOtherReader/1.0"):
            response = self._root(ua)
            root, _ = _parse_links(response.body)
            titles = [e.text for e in root.findall(f"{{{ATOM_NS}}}entry/{{{ATOM_NS}}}title")]
            self.assertIn("Search", titles, ua)


class FacetFeedsTest(unittest.TestCase):
    @mock.patch.object(api_search.search_index, "get_catalog_index")
    def test_authors_landing_lists_authors_with_books_links(self, get_index):
        get_index.return_value = _fake_index()
        response = api_search.author_search(q="", page=1, limit=10, _=None)
        root, links = _parse_links(response.body)

        self.assertIn("kind=navigation", response.media_type)
        search_links = [l for l in links if l.get("rel") == "search"]
        self.assertEqual(search_links[0]["href"], "/opds/authors/search.xml")
        self.assertIn("/opds/authors/search?q={searchTerms}", search_links[1]["href"])

        entries = root.findall(f"{{{ATOM_NS}}}entry")
        titles = [e.findtext(f"{{{ATOM_NS}}}title") for e in entries]
        self.assertEqual(titles, ["Иванов", "Петров"])

        hrefs = [e.find(f"{{{ATOM_NS}}}link").get("href") for e in entries]
        self.assertEqual(hrefs[0], "/opds/authors/books?name=%D0%98%D0%B2%D0%B0%D0%BD%D0%BE%D0%B2")

    @mock.patch.object(api_search.search_index, "get_catalog_index")
    def test_authors_search_filters_by_substring(self, get_index):
        get_index.return_value = _fake_index()
        response = api_search.author_search(q="петр", page=1, limit=10, _=None)
        root, _ = _parse_links(response.body)
        titles = [e.findtext(f"{{{ATOM_NS}}}title") for e in root.findall(f"{{{ATOM_NS}}}entry")]
        self.assertEqual(titles, ["Петров"])

    @mock.patch.object(api_search.search_index, "get_catalog_index")
    def test_author_books_feed_is_acquisition_with_name_in_pagination(self, get_index):
        get_index.return_value = _fake_index()
        response = api_search.author_books(name="Иванов", page=1, limit=1, _=None,
                                           settings=mock.Mock(ABS_BASE="http://abs"))
        root, _ = _parse_links(response.body)
        self.assertIn("kind=acquisition", response.media_type)

        entries = root.findall(f"{{{ATOM_NS}}}entry")
        self.assertEqual(len(entries), 1)
        acq = entries[0].findall(f"{{{ATOM_NS}}}link[@rel='http://opds-spec.org/acquisition']")
        self.assertEqual(acq[0].get("href"), "/acquire/i1/Alpha.epub")

        next_link = root.find(f"{{{ATOM_NS}}}link[@rel='next']")
        self.assertIsNotNone(next_link)
        query = parse_qs(urlparse(next_link.get("href")).query)
        self.assertEqual(query["name"], ["Иванов"])
        self.assertEqual(query["page"], ["2"])

    @mock.patch.object(api_search.search_index, "get_catalog_index")
    def test_unknown_author_gives_empty_acquisition_feed(self, get_index):
        get_index.return_value = _fake_index()
        response = api_search.author_books(name="Никто", page=1, limit=10, _=None,
                                           settings=mock.Mock(ABS_BASE="http://abs"))
        root, _ = _parse_links(response.body)
        self.assertIn("kind=acquisition", response.media_type)
        self.assertEqual(root.findall(f"{{{ATOM_NS}}}entry"), [])

    @mock.patch.object(api_search.search_index, "get_catalog_index")
    def test_genres_feed_and_books(self, get_index):
        get_index.return_value = _fake_index()
        response = api_search.genre_search(q="", page=1, limit=10, _=None)
        root, _ = _parse_links(response.body)
        titles = [e.findtext(f"{{{ATOM_NS}}}title") for e in root.findall(f"{{{ATOM_NS}}}entry")]
        self.assertEqual(titles, ["Фантастика"])

        books = api_search.genre_books(name="Фантастика", page=1, limit=10, _=None,
                                       settings=mock.Mock(ABS_BASE="http://abs"))
        root, _ = _parse_links(books.body)
        self.assertEqual(len(root.findall(f"{{{ATOM_NS}}}entry")), 2)


class BookSearchTest(unittest.TestCase):
    @mock.patch.object(api_search.search_index, "get_catalog_index")
    @mock.patch.object(api_search.abs, "search_items")
    @mock.patch.object(api_search.abs, "list_libraries")
    def test_universal_search_mixes_facets_and_books(self, list_libraries,
                                                     search_items, get_index):
        list_libraries.return_value = [{"id": "lib1", "mediaType": "book", "name": "L"}]
        search_items.return_value = [_item("i1", "Found")]
        get_index.return_value = _fake_index()
        response = api_search.book_search(q="иванов", _=None,
                                          settings=mock.Mock(ABS_BASE="http://abs"))
        root, _ = _parse_links(response.body)
        titles = [e.findtext(f"{{{ATOM_NS}}}title") for e in root.findall(f"{{{ATOM_NS}}}entry")]
        self.assertEqual(titles, ["Author: Иванов", "Found"])

    @mock.patch.object(api_search.search_index, "get_catalog_index")
    @mock.patch.object(api_search.abs, "search_items")
    @mock.patch.object(api_search.abs, "list_libraries")
    def test_book_search_survives_index_failure(self, list_libraries,
                                                search_items, get_index):
        list_libraries.return_value = [{"id": "lib1", "mediaType": "book", "name": "L"}]
        search_items.return_value = [_item("i1", "Found")]
        get_index.side_effect = RuntimeError("index broken")
        response = api_search.book_search(q="Found", _=None,
                                          settings=mock.Mock(ABS_BASE="http://abs"))
        root, _ = _parse_links(response.body)
        titles = [e.findtext(f"{{{ATOM_NS}}}title") for e in root.findall(f"{{{ATOM_NS}}}entry")]
        self.assertEqual(titles, ["Found"])

    @mock.patch.object(api_search.abs, "search_items")
    @mock.patch.object(api_search.abs, "list_libraries")
    def test_empty_query_returns_empty_feed(self, list_libraries, search_items):
        response = api_search.book_search(q="", _=None,
                                          settings=mock.Mock(ABS_BASE="http://abs"))
        root, _ = _parse_links(response.body)
        self.assertEqual(root.findall(f"{{{ATOM_NS}}}entry"), [])
        search_items.assert_not_called()


class OpenSearchDescriptionsTest(unittest.TestCase):
    def test_book_description_keeps_legacy_template(self):
        response = api_search.book_search_description(_=None)
        root = etree.fromstring(response.body)
        template = root.find("{http://a9.com/-/spec/opensearch/1.1/}Url").get("template")
        self.assertEqual(template, "/opds/search?q={searchTerms}")

    def test_author_description_template(self):
        response = api_search.author_search_description(_=None)
        root = etree.fromstring(response.body)
        template = root.find("{http://a9.com/-/spec/opensearch/1.1/}Url").get("template")
        self.assertEqual(template,
                         "/opds/authors/search?q={searchTerms}&page=1&limit=100")


if __name__ == "__main__":
    unittest.main()
