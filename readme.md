## Eco_RAG

> Trying to build a well-structured and efficient RAG system (Personal practice).

### Overview

##### structure of the Eco_RAG system:
```
Eco_RAG/
├── .env                    # API keys and secrets (never commit this)
├── data/                   # DateSets or PDFs, text files
├── db/                     # Vector DB storage
└── src/
    ├── __init__.py         # handle interfaces for outer calls
    ├── Config.py           # Centralized configuration (Models, Paths)
    ├── Schema.py           # Defines what a "Document" looks like
    ├── ContextManager.py   # !User Interface and Manages conversation history and context
    ├── ChatModel.py        # Handles prompt engineering and LLM calls and what Message or Response looks like
    ├── QueryProcessor.py   # !Core module to handle query routing and rewriting
    ├── Retriever.py        # Retrieves relevant documents from vector DB
    ├── Adapter.py          # !Process query results between Retriever and ChatModel, also iterate query if needed
    └── utils/
        ├── __init__.py
        ├── Assembler.py    # Handles files process and interaction with vector DB
        └── ...             
├── web_src/                # other language modules
└── config.json             # global config for all languages
```

##### Flow
```
                                                            System  ->  data      
                                                                         ↓
User -> ContextManager -> ChatModel -> QueryProcessor -> Retriever <-> Assembler <-> VectorDB
                                          ^                      |
                                          └ Iterate <- Adapter <-┘
                                                          |
User <- ContextManager <- ChatModel <---------------------┘(final context)
```
