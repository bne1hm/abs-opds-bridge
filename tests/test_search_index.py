import threading
import unittest
from unittest import mock

from fastapi import HTTPException

from opds_bridge.services import search_index as si
from opds_bridge.services.abs_client import fetch_all_items
from opds_bridge.services.search_index import (
    CatalogIndex,
    FacetBucket,
    build_catalog_index,
    books_by_author,
    books_by_genre,
    clean_facet,
    normalize_facet,
    search_authors,
    search_genres,
    split_authors,
)


def _item(item_id, title, author_name=None, genres=None, ebook=True):
    media = {"metadata": {"title": title}}
    if author_name is not None:
        media["metadata"]["authorName"] = author_name
    if genres is not None:
        media["metadata"]["genres"] = genres
    if ebook:
        media["ebookFormat"] = "epub"
    return {"id": item_id, "media": media}


class FacetNormalization(unittest.TestCase):
    def test_clean_collapses_whitespace(self):
        self.assertEqual(clean_facet("  Богушевская   Ирина  "), "Богушевская Ирина")

    def test_normalize_casefolds(self):
        self.assertEqual(normalize_facet(" Fantasy "), "fantasy")

    def test_split_authors_drops_empty(self):
        self.assertEqual(split_authors(" Иванов , , Петров ,"), ["Иванов", "Петров"])

    def test_split_authors_empty(self):
        self.assertEqual(split_authors(""), [])
        self.assertEqual(split_authors(None), [])


class BuildIndex(unittest.TestCase):
    def setUp(self):
        self.index = build_catalog_index([
            [
                _item("1", "Book One", author_name="Иванов, Петров", genres=["Фантастика"]),
                _item("2", "Book Two", author_name="иванов", genres=["фантастика"]),
                _item("3", "Audio Only", author_name="Иванов", ebook=False),
            ],
            [
                _item("4", "Book Four", genres=["Роман"]),
                _item("1", "Book One dup", author_name="Иванов, Петров"),  # dedup by id
            ],
        ])

    def test_only_ebooks_indexed(self):
        self.assertEqual(set(self.index.items_by_id), {"1", "2", "4"})

    def test_authors_merged_across_libraries_and_case(self):
        labels = {b.label: b for b in self.index.authors}
        self.assertIn("Иванов", labels)
        self.assertIn("Петров", labels)
        self.assertEqual(set(labels["Иванов"].item_ids), {"1", "2"})

    def test_genres_casefolded_and_merged(self):
        labels = {b.label: b for b in self.index.genres}
        self.assertEqual(set(labels["Фантастика"].item_ids), {"1", "2"})
        self.assertEqual(labels["Роман"].item_ids, ("4",))

    def test_authors_sorted_by_label(self):
        labels = [b.label for b in self.index.authors]
        self.assertEqual(labels, sorted(labels, key=str.casefold))

    def test_books_by_author_sorted_by_title(self):
        titles = [it["media"]["metadata"]["title"] for it in books_by_author(self.index, " ИВАНОВ ")]
        self.assertEqual(titles, ["Book One", "Book Two"])

    def test_books_by_genre_exact_normalized_match(self):
        titles = [it["media"]["metadata"]["title"] for it in books_by_genre(self.index, "фантастика")]
        self.assertEqual(titles, ["Book One", "Book Two"])

    def test_unknown_facet_returns_empty(self):
        self.assertEqual(books_by_author(self.index, "Неттакого"), [])
        self.assertEqual(books_by_genre(self.index, "Неттакого"), [])


class FacetSearch(unittest.TestCase):
    def setUp(self):
        self.index = CatalogIndex(
            items_by_id={},
            authors=(
                FacetBucket("bradbury", "Ray Bradbury", ("a",)),
                FacetBucket("bronte", "Charlotte Brontë", ("b",)),
                FacetBucket("толстой", "Лев Толстой", ("c",)),
            ),
            genres=(FacetBucket("fantasy", "Fantasy", ("a",)),),
        )

    def test_substring_search(self):
        found = [b.label for b in search_authors(self.index, "br")]
        self.assertEqual(found, ["Ray Bradbury", "Charlotte Brontë"])

    def test_cyrillic_substring(self):
        found = [b.label for b in search_authors(self.index, "толст")]
        self.assertEqual(found, ["Лев Толстой"])

    def test_empty_query_returns_all(self):
        self.assertEqual(len(search_authors(self.index, "")), 3)
        self.assertEqual(len(search_genres(self.index, "")), 1)

    def test_no_match(self):
        self.assertEqual(search_authors(self.index, "zzz"), [])


class FetchAllItemsTest(unittest.TestCase):
    @mock.patch("opds_bridge.services.abs_client.get_json")
    def test_single_page_with_total(self, get_json):
        get_json.return_value = {"results": [{"id": "a"}, {"id": "b"}], "total": 2}
        self.assertEqual([it["id"] for it in fetch_all_items("lib")], ["a", "b"])
        self.assertEqual(get_json.call_count, 1)

    @mock.patch("opds_bridge.services.abs_client.get_json")
    def test_no_total_paginates_until_empty_page(self, get_json):
        # server caps the page below the requested limit
        get_json.side_effect = [
            {"results": [{"id": "a"}]},
            {"results": [{"id": "b"}]},
            {"results": []},
        ]
        items = fetch_all_items("lib", limit=2000)
        self.assertEqual([it["id"] for it in items], ["a", "b"])
        self.assertEqual(get_json.call_count, 3)
        offsets = [c.kwargs["params"]["offset"] for c in get_json.call_args_list]
        self.assertEqual(offsets, [0, 1, 2])

    @mock.patch("opds_bridge.services.abs_client.get_json")
    def test_server_ignoring_offset_raises_502(self, get_json):
        same = {"results": [{"id": "a"}, {"id": "b"}], "total": 5}
        get_json.return_value = same
        with self.assertRaises(HTTPException) as ctx:
            fetch_all_items("lib")
        self.assertEqual(ctx.exception.status_code, 502)

    @mock.patch("opds_bridge.services.abs_client.get_json")
    def test_empty_page_before_total_raises_502(self, get_json):
        get_json.side_effect = [
            {"results": [{"id": "a"}], "total": 3},
            {"results": [], "total": 3},
        ]
        with self.assertRaises(HTTPException) as ctx:
            fetch_all_items("lib")
        self.assertEqual(ctx.exception.status_code, 502)

    @mock.patch("opds_bridge.services.abs_client._MAX_INDEX_PAGES", 2)
    @mock.patch("opds_bridge.services.abs_client.get_json")
    def test_too_many_pages_raises_502(self, get_json):
        get_json.return_value = {"results": [{"id": "a"}]}  # no total, never empty
        with self.assertRaises(HTTPException) as ctx:
            fetch_all_items("lib")
        self.assertEqual(ctx.exception.status_code, 502)


class GetCatalogIndexTest(unittest.TestCase):
    def setUp(self):
        si._index_cache = si.Cache(default_ttl=600, maxsize=4)

    @mock.patch.object(si.abs_client, "fetch_all_items")
    @mock.patch.object(si.abs_client, "list_libraries")
    def test_builds_once_and_caches(self, list_libraries, fetch_all):
        list_libraries.return_value = [{"id": "lib1", "mediaType": "book"}]
        fetch_all.return_value = [
            _item("1", "Book", author_name="A", genres=["G"]),
        ]
        first = si.get_catalog_index()
        second = si.get_catalog_index()
        self.assertIs(first, second)
        self.assertEqual(fetch_all.call_count, 1)

    @mock.patch.object(si.abs_client, "fetch_all_items")
    @mock.patch.object(si.abs_client, "list_libraries")
    def test_failed_build_is_not_cached(self, list_libraries, fetch_all):
        list_libraries.return_value = [{"id": "lib1", "mediaType": "book"}]
        fetch_all.side_effect = [HTTPException(502), [_item("1", "Book", author_name="A")]
        ]
        with self.assertRaises(HTTPException):
            si.get_catalog_index()
        index = si.get_catalog_index()
        self.assertIn("1", index.items_by_id)

    @mock.patch.object(si.abs_client, "fetch_all_items")
    @mock.patch.object(si.abs_client, "list_libraries")
    def test_concurrent_cold_start_builds_once(self, list_libraries, fetch_all):
        list_libraries.return_value = [{"id": "lib1", "mediaType": "book"}]
        fetch_all.return_value = [_item("1", "Book", author_name="A")]

        barrier = threading.Barrier(4)
        results = []

        def worker():
            barrier.wait()
            results.append(si.get_catalog_index())

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(fetch_all.call_count, 1)
        self.assertTrue(all(r is results[0] for r in results))


if __name__ == "__main__":
    unittest.main()
