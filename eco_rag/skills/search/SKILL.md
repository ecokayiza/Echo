---
name: search
description: Unified Eco_RAG retrieval guidance for choosing and using local vector
  database search and public web search. Use when a workflow needs local indexed evidence,
  fresh external facts, public documentation, citations, or a decision between database_search,
  web_search, and web_fetch.
---

# Search

Use this skill to choose between local database evidence, web search results, and fetched web page text.

## Tool Choice

- Use `database_search("query", top_k=3)` for indexed project files, user-provided documents, stored notes, local knowledge, and questions that should be grounded in the active Eco_RAG database.
- Use `web_search("query", max_results=5)` to find candidate public sources for fresh facts, official pages, documentation, and citations.
- Use `web_fetch("https://example.com/page", max_chars=8000)` to read a specific result when snippets are not enough to answer.
- Use database search before web search when local indexed evidence may answer the question.
- Use web search after database search when local results are empty, weak, stale, or clearly missing external context.
- Use web fetch after web search when the answer needs page-body evidence from one promising URL.
- Use both when the answer needs local project context plus external verification.
- Web search uses the configured backend from Runtime Settings. Do not pass or invent backend arguments.

## Query Discipline

- Write focused natural-language queries with the concrete subject and needed detail.
- Keep result counts small: prefer `top_k=3` to `5` and `max_results=5` to `7`.
- Avoid repeating the same search without adding a sharper term, source name, date, or constraint.
- Stop retrieving once the evidence is enough to answer.

## Evidence Handling

- Prefer local database evidence for claims about indexed files or user-provided material.
- Prefer trustworthy web sources for external facts; cite URLs when web results inform the answer.
- Prefer fetched page text over search snippets for detailed claims.
- If retrieved evidence conflicts, say what differs and prefer the source that best matches the user's requested scope.
- If both tools return weak evidence, explain the uncertainty instead of overstating the answer.
