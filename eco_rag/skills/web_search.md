# web_search

## Purpose

Search the public web for fresh or external information that is not likely to exist in the local vector database.

## When To Use

- The query depends on current events, external facts, or sources outside the local knowledge base.
- Local retrieval returns little or no useful evidence.

## Inputs

- `query`: the web query in natural language.
- `max_results`: optional result count. Prefer `3` to `5`.

## Output

Returns a JSON object with:

- `type: "context"`
- `skill_name: "web_search"`
- `items`: a list of context items with `title`, `content`, and `url` when available

## Guidance

- Keep the number of results small and focused.
- If the result set is empty, move on instead of retrying the same query many times.
- When you have enough evidence, stop using tools and return the retrieve decision JSON.
