# Echo RAG Eval

## Index

Use `wiki18_100w` as the database with the `E5-base-v2` embedder.

The retrieval corpus is large and must be downloaded manually. Download `wiki18_100w` from ModelScope:
```text
https://www.modelscope.cn/datasets/hhjinjiajie/FlashRAG_Dataset/tree/master/retrieval_corpus
```
we have prepared the download script, after it, put the corpus under `tests/data/retrieval_corpus`, including `wiki18_100w.jsonl` and `e5_flat_inner.index`

the corpus has prebuilt FAISS index with e5-base-v2, we prepared local embedding model serivce, you can launch it with
```bash
python -m mcp_server.local_e5_embedder --host 127.0.0.1 --port 8101 --model intfloat/e5-base-v2
```

then **replace search skill  with `SKILL-eval.md`** to allow database_search only for evaluation.

Before testing, you should ***set the active chat and embedding model*** in `models.json`. If the active embedding model points 

## Train
- - From HotpotQA train including 1000 records with easy medium hard:
- - counts={'easy': 400, 'hard': 300, 'medium': 300};
- - available={'easy': 17972,'medium': 56814, 'hard': 15661}
- use chatgpt-5.5
- replace system prompt with `system-train.yaml` , for `<echo_think>`, include validation deciding if the previous tool call is valid
- not valid tool call will not be present inside sample
- only sample with correct final answer will be in trainning dataset

## Test
- Use HotpotQA as the test dataset.
- Use token-level F1 score as the metric.

eval script launch example:
```bash
python tests/eval/flashrag_hotpotqa_eval.py \
  --hotpotqa-path tests/data/hotpotqa/dev.jsonl \
  --max-questions 1000 \
  --concurrency 8
```
for trainning, use the `tests/data/hotpotqa/train-extrat.jsonl` dataset which includes 1000 questions


## Guidance

Baselines:

- auto-rag: llama3-8b at `44.9`
- qwen3.5-9b with the system

Ours:

- finetuned llama3-8b with the system
- finetuned qwen3.5-9b with the system

The system uses `database_search` only at eval.
