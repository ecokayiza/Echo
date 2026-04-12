# Integration Tests

这里放跨模块集成测试。

适合放在这里的场景：

- API + ChatService + WorkflowService 联调
- SSE streaming 行为
- database / vector store / retrieval 联调
- session 持久化与恢复
- Web 客户端依赖的接口契约验证

原则：

- 可以跨多个模块
- 可以读写测试用磁盘数据
- 但尽量不要依赖真实外部线上服务
