# database_search

## Purpose

Search the local Eco_RAG vector database for semantically relevant chunks.

## When To Use

- The user is asking about project knowledge, indexed files, stored documentation, or past imported content.
- You need grounded local evidence before answering.

## Inputs

- `query`: the search query in natural language.
- `top_k`: optional result count. Prefer small values such as `3` to `5`.

## Output

Returns a JSON object with:

- `type: "context"`
- `skill_name: "database_search"`
- `items`: a list of context items containing titles, content, and source metadata

## Guidance

- Prefer this skill before web search when the answer may already be in the indexed knowledge base.
- If results are empty or weak, you may try `web_search` or load another skill.
