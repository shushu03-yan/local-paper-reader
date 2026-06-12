from __future__ import annotations

import re


PAGE_ANCHOR_RE = re.compile(r"<!--\s*page:\s*(\d+)\s*-->")


def split_markdown_pages(markdown: str) -> dict[int, str]:
    matches = list(PAGE_ANCHOR_RE.finditer(markdown))
    if not matches:
        content = markdown.strip()
        return {1: content} if content else {}

    pages: dict[int, str] = {}
    for index, match in enumerate(matches):
        page_number = int(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        pages[page_number] = markdown[start:end].strip()
    return pages
