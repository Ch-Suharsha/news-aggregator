"""Blog and newsletter content extraction."""

import hashlib

from bs4 import BeautifulSoup


def extract_full_context(html: str) -> tuple[str, str, str]:
    """Return cleaned HTML, full readable text, and a stable content hash."""
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "template", "svg"]):
        node.decompose()
    cleaned_html = str(soup.body or soup)
    text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
    return cleaned_html, text, hashlib.sha256(text.encode("utf-8")).hexdigest()
