"""Allow-list HTML sanitizer (stdlib only) for admin-authored rich text.

Keeps basic formatting produced by the cabinet's rich-text editor and strips
everything else — scripts, event handlers, styles, iframes, unknown tags,
javascript: links. Output is re-serialised, so malformed input cannot smuggle
raw markup through.
"""

from __future__ import annotations

from html import escape
from html.parser import HTMLParser

ALLOWED_TAGS = {
    "p", "br", "b", "strong", "i", "em", "u", "s",
    "h1", "h2", "h3", "h4",
    "ul", "ol", "li",
    "a", "div", "span", "blockquote",
}
_VOID = {"br"}
_SAFE_HREF = ("http://", "https://", "mailto:", "tel:")


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_TAGS:
            return
        if tag == "a":
            href = next((v for k, v in attrs if k == "href"), None) or ""
            if not href.lower().startswith(_SAFE_HREF):
                href = "#"
            self.out.append(
                f'<a href="{escape(href, quote=True)}" target="_blank" rel="noopener noreferrer">'
            )
        else:
            self.out.append(f"<{tag}>")  # all attributes dropped
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag not in ALLOWED_TAGS or tag in _VOID or tag not in self.stack:
            return
        while self.stack:  # close any unclosed children first
            top = self.stack.pop()
            self.out.append(f"</{top}>")
            if top == tag:
                break

    def handle_data(self, data: str) -> None:
        self.out.append(escape(data))

    def close(self) -> None:
        super().close()
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")


def sanitize_html(raw: str | None) -> str:
    parser = _Sanitizer()
    parser.feed(raw or "")
    parser.close()
    return "".join(parser.out)
