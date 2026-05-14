---
name: search
description: Unified Echo retrieval guidance for choosing and using date/time,
  local vector database search, and public web search. Use when a workflow needs
  current date or time, local indexed evidence, fresh external facts, public documentation,
  citations, or a decision between date, database_search, web_search, and web_fetch.
---

# Search

Use this skill to choose between current date/time, local database evidence, web search results, and fetched web page text.

## Tool Choice

- Use `date(timezone=None)` for the current date, current time, weekday, timezone, and questions about today, tomorrow, or yesterday.
- Use `database_search("query", top_k=3)` for indexed project files, user-provided documents, stored notes, local knowledge, and questions that should be grounded in the active Echo database.
- Use `web_search("query", max_results=5)` to find candidate public sources for fresh facts, official pages, documentation, and citations.
- Use `web_fetch("https://example.com/page", max_chars=8000)` to read a specific result when snippets are not enough to answer.
- Call retrieval tools through the provider-native tool calling channel; never print XML tags like `<web_fetch>` or JSON tool payloads as text.
- Use `web_search` instead of `date` only when the user asks for external current facts beyond date/time.
- Use database search before web search when local indexed evidence may answer the question.
- Use web search after database search when local results are empty, weak, stale, or clearly missing external context.
- Use web fetch after web search when the answer needs page-body evidence from one promising URL.
- Use both when the answer needs local project context plus external verification.
- Web search uses the configured backend from Runtime Settings. Do not pass or invent backend arguments.

## Query Discipline

- **Write focused natural-language queries with the concrete subject and needed detail**.
- Keep result counts small: prefer `top_k=3` to `5` and `max_results=5` to `7`.
- Avoid repeating the same search without adding a sharper term, source name, date, or constraint.
- Stop retrieving once the evidence is enough to answer.

## Evidence Handling

- Prefer local database evidence for claims about indexed files or user-provided material.
- Prefer trustworthy web sources for external facts; cite URLs when web results inform the answer.
- Prefer fetched page text over search snippets for detailed claims.
- If `web_fetch` returns no readable text, use another source or rely on an attached screenshot only when the active model supports vision.
- If retrieved evidence conflicts, say what differs and prefer the source that best matches the user's requested scope.
- If both tools return weak evidence, explain the uncertainty instead of overstating the answer.
