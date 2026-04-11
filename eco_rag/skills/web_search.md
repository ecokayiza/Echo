# web_search

## Purpose

Search the public web for fresh or external information that is unlikely to exist in the local vector database.

## When To Use

- The answer depends on current events, external facts, public documentation, or third-party sources.
- The user explicitly asks for web results, latest information, or outside sources.
- Local retrieval is weak, empty, or clearly mismatched.

## When Not To Use

- The question is mainly about repo code, indexed notes, or other local knowledge.
- The current context already contains enough evidence to answer.
- You would just repeat the same search without a sharper query.

## Inputs

- `query`: the web query in natural language.
- `max_results`: optional result count. Prefer `3` to `5`; keep it small.

## Output

Returns a JSON object with:

- `type: "context"`
- `skill_name: "web_search"`
- `items`: a list of context items with `title`, `content`, and `url` when available

## Guidance

- Write a focused query that includes the concrete subject, not vague filler.
- Prefer one good search over many similar retries.
- Use small result counts unless the first batch is clearly weak.
- Prefer trustworthy pages and concrete evidence over generic SEO pages.
- If the result set is empty or noisy, either refine the query once or stop.
- Once you have enough evidence to answer, stop searching and move the workflow forward.
