from __future__ import annotations

import re

WORKFLOW_SECTION_NAMES = {"plan", "think", "retrieve", "answer", "tool"}
TAG_PATTERN = re.compile(r"</?([a-z_]+)>", re.IGNORECASE)


def parse_workflow_sections(content: str | None, *, allow_unclosed: bool = False) -> dict[str, str]:
    """Parse XML-style workflow blocks."""
    return {name: block for name, block in workflow_section_entries(content, allow_unclosed=allow_unclosed)}


def workflow_section_entries(content: str | None, *, allow_unclosed: bool = False) -> list[tuple[str, str]]:
    """Return workflow blocks in source order."""
    text = (content or "").strip()
    return _section_entries(text, allow_unclosed=allow_unclosed)


def render_workflow_section(name: str, content: str) -> str:
    """Render one workflow block in the preferred XML-style format."""
    tag = name.strip().lower()
    return f"<{tag}>\n{content.strip()}\n</{tag}>".strip()


def render_workflow_sections(entries: list[tuple[str, str]]) -> str:
    """Render workflow blocks in source order."""
    return "\n\n".join(render_workflow_section(name, content) for name, content in entries).strip()


def _section_entries(text: str, *, allow_unclosed: bool) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    current: str | None = None
    block_start = 0

    for match in TAG_PATTERN.finditer(text):
        tag_name = match.group(1).lower()
        if not _is_section_name(tag_name):
            continue

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

    if current is not None:
        if not allow_unclosed:
            return entries
        entries.append((current, text[block_start:].strip()))

    return entries


def _is_section_name(name: str) -> bool:
    return name.strip().lower() in WORKFLOW_SECTION_NAMES
