# Available Skills

These skills are available to the workflow retrieve agent. Read this catalog first, then load a specific skill with the `load_skill` tool only when you need the full instructions.

## Default Skills

- `database_search`
  - Search the local Eco_RAG vector database for semantically related document chunks.
  - Use it when the answer may already exist in indexed project knowledge.
  - Returns context items with source metadata and similarity distance when available.
  [fobidden now]

- `web_search`
  - Search the public web for fresh or external information.
  - Use it when local knowledge is not enough or the user asks about current events or outside knowledge.
  - Returns a small list of titles, snippets, and URLs.

## Optional Loading Pattern

- If you are unsure how to use a skill, call `load_skill` with the skill name.
- After reading the loaded skill, decide whether to call a search tool or finish retrieval.
- When retrieval is complete, return strict JSON with `next_step` and `reason`.
