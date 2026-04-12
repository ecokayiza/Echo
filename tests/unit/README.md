# Unit Tests

这里放快速、隔离、无外部依赖的单元测试。

当前重点覆盖：

- `eco_rag/chat/`
- `eco_rag/workflow/`
- `eco_rag/tools/`
- `apps/api` 的核心接口行为

单元测试应该优先验证：

- workflow 路由和恢复
- session / message 持久化语义
- SSE 事件适配
- context compaction 规则
- database 与 embedding model 的配对约束

推荐运行方式：

```bash
conda run -n llm python -m unittest
```
