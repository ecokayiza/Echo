## Eco_RAG

> Trying to build a well-structured and efficient RAG system (Personal practice).

### Overview

structure of the Eco_RAG system:

```
Eco_RAG/
├── .env                    # API keys and secrets (never commit this)
├── .gitignore              # ignore  files for git
├── data/                   # DateSets or PDFs, text files
├── db/                     # Vector DB storage
└── src/
    ├── __init__.py         # handle interfaces for outer calls
    ├── config.py           # Centralized configuration (Models, Paths)
    ├── main.py             # Entry point to run the app
    ├── schema.py           # Defines what a "Document" or "Response" looks like

    └── utils/
        ├── __init__.py
        ├── assembler.py    # Handles files process and interaction with vector DB
        ├── api.py          # Handles prompt engineering and LLM calls
        └── ...             
...
├── web_src/                # other language modules
└── config.json             # global config for all languages
```