"""Blog and newsletter content extraction."""

import hashlib

from bs4 import BeautifulSoup
import trafilatura


def extract_full_context(html: str) -> tuple[str, str, str]:
    """Return cleaned HTML, full readable text, and a stable content hash."""
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "template", "svg"]):
        node.decompose()
    cleaned_html = str(soup.body or soup)
    text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
    return cleaned_html, text, hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_markdown(html: str, *, url: str | None = None) -> str:
    """Extract readable article content as Markdown."""
    markdown = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_links=True,
        include_tables=True,
        favor_recall=True,
    )
    if not markdown or not markdown.strip():
        raise ValueError(f"Could not extract Markdown content from {url or 'page'}")
    return markdown.strip()
