# Echo RAG Eval

## Index

Use `wiki18_100w` as the database with the `E5-base-v2` embedder.

The retrieval corpus is large and must be downloaded manually. Download `wiki18_100w` from ModelScope:

```text
https://www.modelscope.cn/datasets/hhjinjiajie/FlashRAG_Dataset/tree/master/retrieval_corpus
```

Keep the corpus outside Git, for example:

```text
tests/eval/retrieval_corpus/wiki18_100w.zip
```

Index a small smoke-test slice:

```bash
python tests/eval/flashrag_hotpotqa_eval.py ^
  --index-wiki ^
  --corpus-path tests/eval/retrieval_corpus/wiki18_100w.zip ^
  --database-name wiki18_100w ^
  --embedding-model-name E5-base-v2 ^
  --backend faiss ^
  --max-corpus-docs 10000 ^
  --no-evaluate
```

Index the full corpus by setting `--max-corpus-docs 0`.

## Train

- 10,000 records.
- From Natural Questions (NQ) and 2WikiMultihopQA (2Wiki).

## Test

- Use HotpotQA as the test dataset.
- Use F1 score as the metric.
- The eval script uses the local file at `tests/eval/hotpotqa/dev.jsonl` by default for the `dev` split. Pass `--hotpotqa-path` for a different local JSONL file.

Run retrieval evaluation:

```bash
python tests/eval/flashrag_hotpotqa_eval.py ^
  --database-name wiki18_100w ^
  --hotpotqa-path tests/eval/hotpotqa/dev.jsonl ^
  --max-questions 50 ^
  --top-k 4
```

Run FlashRAG prebuilt-index evaluation:

First launch the local E5 embedding service manually:

```bash
python -m mcp_server.local_e5_embedder --host 127.0.0.1 --port 8092 --model intfloat/e5-base-v2
```

Then run the eval against the prebuilt FAISS index:

```bash
python tests/eval/flashrag_hotpotqa_eval.py ^
  --retriever flashrag-index ^
  --database-name wiki18_100w ^
  --corpus-path D:\Datasets\FlashRAG\wiki18_100w.jsonl ^
  --flashrag-index-path D:\Datasets\FlashRAG\wiki18_100w_e5_index\index.faiss ^
  --hotpotqa-path tests/eval/hotpotqa/dev.jsonl ^
  --local-e5-base-url http://127.0.0.1:8092/v1 ^
  --local-e5-model intfloat/e5-base-v2
```

The script will create `wiki18_100w.jsonl.offsets.u64` automatically when it is missing.

The summary JSON reports:

- `average_f1`: token-overlap F1 between gold answers and retrieved text.
- `hit_rate`: exact normalized answer string presence in retrieved text.
- `examples`: sampled questions with retrieved titles and per-example F1.

## Guidance

Baselines:

- auto-rag: llama3-8b at `44.9`
- qwen3.5-9b with the system

Ours:

- finetuned llama3-8b with the system
- finetuned qwen3.5-9b with the system

The system uses `database_search` and `web_search`.
