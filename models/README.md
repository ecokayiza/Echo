# Models

这个目录放模型文件，以及和模型强绑定的本地服务脚本。

## Qwen3 Embedding Service

脚本：

- `models/qwen3_embedding_service.py`

职责：

- 单独启动一个 OpenAI 兼容 embedding 服务
- 首次启动时把 `Qwen/Qwen3-Embedding-0.6B` 下载到 `models/Qwen3-Embedding-0.6B`
- 对外暴露：
  - `GET /health`
  - `POST /v1/embeddings`

建议运行方式：

```powershell
conda run -n llm python models/qwen3_embedding_service.py
```

默认地址：

- `http://127.0.0.1:8091/v1`

然后把主项目里的 `models.json` embedding model `base_url` 指向这个地址。

这个脚本是独立服务，不由 `apps/api` 托管。
