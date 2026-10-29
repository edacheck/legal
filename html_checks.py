"""Extract article text and validate links within a single edition."""

from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.article = []
        self.links = []
        self.identifiers = set()
        self.resources = []

    def handle_starttag(self, tag, attributes):
        values = dict(attributes)
        if tag == "article":
            self.inside = True
        if "id" in values:
            self.identifiers.add(values["id"])
        if "href" in values:
            self.links.append(values["href"])
        if "src" in values or tag in {"script", "iframe", "form"}:
            self.resources.append(values.get("src", tag))

    def handle_endtag(self, tag):
        if tag == "article":
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.article.append(data)


def links(path, parsed, output):
    if parsed.resources:
        raise ValueError(f"Unexpected active or external resource: {path}")
    for reference in parsed.links:
        target = urlsplit(reference)
        if target.scheme in {"https", "mailto"}:
            continue
        if target.scheme or target.netloc:
            raise ValueError(f"Unexpected link scheme: {reference}")
        destination = (path.parent / unquote(target.path)).resolve() if target.path else path.resolve()
        if not destination.is_relative_to(output.resolve()) or not destination.is_file():
            raise ValueError(f"Broken or escaping local link: {reference}")
        if target.fragment:
            anchor = Page()
            anchor.feed(destination.read_text(encoding="utf-8"))
            if unquote(target.fragment) not in anchor.identifiers:
                raise ValueError(f"Missing anchor: {reference}")
