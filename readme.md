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
    ├── Orchestrator.py     # !Core. Judge overall flow control
    ├── ContextManager.py   # !Core. Manages conversation history
    ├── ChatModel.py        # Handles prompt engineering and LLM calls and what Message or Response looks like
    ├── QueryProcessor.py   # !Core. Handle query. Routing and Rewriting
    ├── Retriever.py        # Retrieves relevant documents from vector DB
    ├── Adapter.py          # !Core. Process query results between Retriever and ChatModel, also iterate query if needed
    └── indexing/
        ├── __init__.py
        ├── Assembler.py    # Handles files process and interaction with vector DB
        └── ...             
├── web_src/                # other language modules
└── config.json             # global config for all languages
```

##### Flow
```
                                                System  ->  data      
                            (Pre Process)                    ↓
User -> System ---------------> QueryProcessor -> Retriever <-> Assembler <-> VectorDB 
                                ↑     1|  ↑              |(Sparse+Dense)            (Graph?)
            ┌-   ContextManager ┘3     |  └-- Adapter ---┘
            ↓         |                ↓        2| (Rerank and Format)
User <- System    ChatModel <--------------------┘ (Final context)
                          4
```

Orchestrator(LLM) steps in:
```
1: Query route.                 Also for Recursive Retrival.  -> sub-problems
2: Judge on retrieved results.  Also for Iterative Retrival.  -> more context
3: Judge on generated response. Also for Adaptive generation. -> regenerate or stop
```

User Profile steps in:
```
1: Personalized Query Rewriting.         -> user style
2: Personalized Document Ranking.        -> user preference
4: Personalized Response Generation.     -> user tone
```

### TODO
  - [x] Basic Indexing and API calls
  - [ ] ChatModel and Context
  - [ ] Longterm、Recent、Task Memory
  - [ ] Retriever:Sparse + Dense Hybrid Retrieval
  - [ ] Adapter and Rerank
  - [ ] QueryProcessor and Orchestrator 
  - [ ] Tracing and Evaluation methods 
  - [ ] Record update(citation) and Graph?