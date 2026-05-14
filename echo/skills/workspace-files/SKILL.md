---
name: workspace-files
description: Read, inspect, create, and edit UTF-8 text files inside Echo's bounded
  workspace root. Use when the user asks to list workspace files, read local workspace
  content, create notes or drafts, or make exact text edits to workspace files.
---

# Workspace Files

Use this skill to work with user-editable local text files in the workspace root.

## Boundaries

- Treat the workspace as the root. Use `.` for the root in tool calls.
- Do not reveal or depend on the backing filesystem directory.
- Do not use absolute paths, `..`, repo paths, or any path outside the workspace root.
- Work with UTF-8 text files only.
- Read before editing unless the user provides the full exact content to write.
- Prefer exact replacement edits over full rewrites for existing files.

## Tools

- `workspace_list_files(path=".", recursive=False, max_results=100)` lists workspace files and directories.
- `workspace_read_file(file_path, max_chars=20000)` reads one text file.
- `workspace_write_file(file_path, content, overwrite=False)` creates a file; pass `overwrite=True` only when replacing the whole file is intended.
- `workspace_edit_file(file_path, old_text, new_text, expected_replacements=1)` replaces exact text in an existing file.

## Workflow

- If the user does not give a path, list the workspace first.
- If editing an existing file, read it first and choose an `old_text` snippet that is unique and includes enough surrounding context.
- If `workspace_edit_file` reports the wrong replacement count, read the file again and use a more exact snippet.
- After creating or editing important content, summarize the path changed and what changed.
