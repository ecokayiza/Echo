# Desktop App Scaffold

这个目录目前保留给未来的桌面壳层，还没有正式接入。

当前项目的真实可用入口是：

- `apps/api`
- `apps/web`

如果后续接 Tauri / Electron，建议保持边界：

- 桌面壳只负责窗口、文件系统权限、原生集成
- 业务逻辑继续留在 `eco_rag/`
- HTTP / SSE 接口继续由 `apps/api` 提供
- 现有 Web UI 可以尽量复用
