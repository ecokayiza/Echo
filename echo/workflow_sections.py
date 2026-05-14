from __future__ import annotations

import re

WORKFLOW_SECTION_NAMES = {"plan", "think", "answer", "tool"}
TAG_PATTERN = re.compile(r"</?echo_(plan|think|answer|tool)>", re.IGNORECASE)


def parse_workflow_sections(content: str | None, *, allow_unclosed: bool = False) -> dict[str, str]:
    """Parse current Echo workflow blocks."""
    return {name: block for name, block in workflow_section_entries(content, allow_unclosed=allow_unclosed)}


def workflow_section_entries(content: str | None, *, allow_unclosed: bool = False) -> list[tuple[str, str]]:
    """Return current Echo workflow blocks in source order."""
    text = (content or "").strip()
    entries: list[tuple[str, str]] = []
    current: str | None = None
    block_start = 0

    for match in TAG_PATTERN.finditer(text):
        tag_name = match.group(1).lower()
        is_close = text[match.start() + 1] == "/"
        if current is None:
            if not is_close:
                current = tag_name
                block_start = match.end()
            continue
        if is_close and tag_name == current:
            entries.append((current, text[block_start:match.start()].strip()))
            current = None
            continue
        if not is_close:
            nested_content = text[block_start:match.start()].strip()
            if nested_content:
                entries.append((current, nested_content))
            current = tag_name
            block_start = match.end()

    if current is not None and allow_unclosed:
        entries.append((current, text[block_start:].strip()))

    return entries


def render_workflow_section(name: str, content: str) -> str:
    """Render one current Echo workflow block."""
    cleaned = name.strip().lower()
    if cleaned not in WORKFLOW_SECTION_NAMES:
        raise ValueError(f"Unknown workflow section '{name}'.")
    return f"<echo_{cleaned}>\n{content.strip()}\n</echo_{cleaned}>".strip()


def render_workflow_sections(entries: list[tuple[str, str]]) -> str:
    """Render current Echo workflow blocks in source order."""
    return "\n\n".join(render_workflow_section(name, content) for name, content in entries).strip()
