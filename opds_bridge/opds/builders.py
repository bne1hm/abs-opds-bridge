import re
import datetime as dt
from typing import Dict, Mapping, Optional
from urllib.parse import quote, urlencode
from lxml import etree
from opds_bridge.opds.atom import feed_type

MIME_BY_EXT = {
    "epub": "application/epub+zip",
    "pdf": "application/pdf",
    "mobi": "application/x-mobipocket-ebook",
    "azw3": "application/x-mobi8-ebook",
    "cbz": "application/x-cbz",
    "cbr": "application/x-cbr",
}

def guess_mime(rel_path: str) -> str:
    ext = (rel_path.rsplit(".", 1)[-1] if "." in rel_path else "").lower()
    return MIME_BY_EXT.get(ext, "application/octet-stream")

def _safe_filename(name: str) -> str:
    name = name.strip()
    name = re.sub(r'[\\/:*?"<>|]+', ' ', name)
    name = re.sub(r'\s+', ' ', name)
    return name.strip()

def _ext_from_item(item: dict) -> str:
    media = (item.get("media") or {})
    ebook = media.get("ebookFile") or {}
    meta = ebook.get("metadata") or {}
    ext = (meta.get("ext") or "").lstrip(".").lower()
    if not ext:
        fmt = (ebook.get("ebookFormat") or media.get("ebookFormat") or "").lower()
        ext = {"epub":"epub","pdf":"pdf","mobi":"mobi","azw3":"azw3","cbz":"cbz","cbr":"cbr"}.get(fmt, "")
    return ext or "bin"

def make_book_entry(feed, item: Dict, abs_base: str):
    media = (item.get("media") or {})
    meta = media.get("metadata") or {}
    title = meta.get("title") or item.get("title") or item["id"]

    entry = etree.SubElement(feed, "entry")
    etree.SubElement(entry, "id").text = f"urn:abs:item:{item['id']}"
    etree.SubElement(entry, "title").text = title
    etree.SubElement(entry, "updated").text = dt.datetime.utcnow().isoformat() + "Z"

    author_name = meta.get("authorName")
    if author_name:
        a = etree.SubElement(entry, "author")
        etree.SubElement(a, "name").text = author_name
    for aobj in (meta.get("authors") or []):
        a = etree.SubElement(entry, "author")
        etree.SubElement(a, "name").text = aobj.get("name") or str(aobj)

    cover = (media.get("cover") or {}).get("contentUrl") or media.get("coverPath")
    if cover:
        base = abs_base.rstrip("/")
        link_img = etree.SubElement(entry, "link")
        link_img.set("rel", "http://opds-spec.org/image")
        link_img.set("href", base + cover)
        link_img.set("type", "image/jpeg")
        link_th = etree.SubElement(entry, "link")
        link_th.set("rel", "http://opds-spec.org/image/thumbnail")
        link_th.set("href", base + cover)
        link_th.set("type", "image/jpeg")

    ext = _ext_from_item(item)
    filename = _safe_filename(title) + f".{ext}"
    slug = quote(filename)
    href = f"/acquire/{item['id']}/{slug}"
    acq = etree.SubElement(entry, "link")
    acq.set("rel", "http://opds-spec.org/acquisition")
    acq.set("href", href)
    acq.set("type", MIME_BY_EXT.get(ext, "application/octet-stream"))

    if meta.get("description"):
        s = etree.SubElement(entry, "summary")
        s.text = meta["description"]

    return entry

def add_pagination_links(feed, base_path: str, page: int, limit: int, has_next: bool,
                         kind: str = "acquisition",
                         params: Optional[Mapping[str, str]] = None):
    """
    Add <link rel="next"> and <link rel="previous"> if applicable,
    preserving extra query params (e.g. search terms, facet names).
    """
    def link(rel, p):
        query = dict(params or {})
        query["page"] = p
        query["limit"] = limit
        l = etree.SubElement(feed, "link")
        l.set("rel", rel)
        l.set("href", f"{base_path}?{urlencode(query)}")
        l.set("type", feed_type(kind))
    if page > 1:
        link("previous", page - 1)
    if has_next:
        link("next", page + 1)
