import datetime as dt
from lxml import etree

OPENSEARCH_MEDIA_TYPE = "application/opensearchdescription+xml"

def feed_type(kind: str = "acquisition") -> str:
    return f"application/atom+xml;profile=opds-catalog;kind={kind}"

def atom_root(title: str, href_self: str, kind: str = "acquisition"):
    nsmap = {None: "http://www.w3.org/2005/Atom",
             "opds": "http://opds-spec.org/2010/catalog"}
    feed = etree.Element("feed", nsmap=nsmap)
    etree.SubElement(feed, "id").text = href_self
    etree.SubElement(feed, "title").text = title
    etree.SubElement(feed, "updated").text = dt.datetime.utcnow().isoformat() + "Z"

    link_self = etree.SubElement(feed, "link")
    link_self.set("rel", "self")
    link_self.set("href", href_self)
    link_self.set("type", feed_type(kind))
    return feed

def add_nav_entry(feed, title: str, href: str, kind: str = "acquisition",
                  entry_id: str | None = None):
    entry = etree.SubElement(feed, "entry")
    etree.SubElement(entry, "id").text = entry_id or href
    etree.SubElement(entry, "title").text = title
    etree.SubElement(entry, "updated").text = dt.datetime.utcnow().isoformat() + "Z"
    link = etree.SubElement(entry, "link")
    link.set("rel", "subsection")
    link.set("type", feed_type(kind))
    link.set("href", href)
    return entry

def add_search_links(feed, description_href: str, template_href: str, kind: str = "acquisition"):
    """Attach both machine-readable search links to a feed.

    The OpenSearchDescription link comes first (FBReader, KOReader);
    the Atom template with {searchTerms} is the fallback Moon+ Reader
    substitutes the query into.
    """
    description = etree.SubElement(feed, "link")
    description.set("rel", "search")
    description.set("href", description_href)
    description.set("type", OPENSEARCH_MEDIA_TYPE)

    fallback = etree.SubElement(feed, "link")
    fallback.set("rel", "search")
    fallback.set("href", template_href)
    fallback.set("type", feed_type(kind))

def add_search_entry(feed, title: str, description_href: str, summary: str):
    """Navigation entry opening the reader's search dialog (FBReader)."""
    entry = etree.SubElement(feed, "entry")
    etree.SubElement(entry, "id").text = "search"
    etree.SubElement(entry, "title").text = title
    etree.SubElement(entry, "updated").text = dt.datetime.utcnow().isoformat() + "Z"
    etree.SubElement(entry, "content").text = summary

    link = etree.SubElement(entry, "link")
    link.set("rel", "search")
    link.set("href", description_href)
    link.set("type", OPENSEARCH_MEDIA_TYPE)
    return entry

def make_opensearch_description(short_name: str, description: str,
                                template: str, kind: str = "acquisition"):
    opensearch = etree.Element("OpenSearchDescription",
                               nsmap={None: "http://a9.com/-/spec/opensearch/1.1/"})
    etree.SubElement(opensearch, "ShortName").text = short_name
    etree.SubElement(opensearch, "Description").text = description
    etree.SubElement(opensearch, "InputEncoding").text = "UTF-8"
    etree.SubElement(opensearch, "OutputEncoding").text = "UTF-8"

    url = etree.SubElement(opensearch, "Url")
    url.set("type", feed_type(kind))
    url.set("template", template)
    return opensearch
