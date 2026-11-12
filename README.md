# 标书 Agent

面向标书资料整理、需求响应、章节编写与质量核对的专用本机工作台，以 DeepSeek Harness 为唯一 Agent 执行底座。

当前处于第一阶段工程开发：已有工作台、业务版本与任务管理、Harness 插件和合成场景检查。默认使用合成资料和本机模型替身；真实模型、真实标书质量和最终交付能力尚未验证。完整业务目标见需求与实施计划。

## 工程结构

| 目录 | 职责 |
| --- | --- |
| `backend/` | Python / FastAPI 业务 API、任务 Worker、数据库迁移和测试 |
| `frontend/` | React / TypeScript / Vite 工作台和 Playwright 场景 |
| `runtime/` | Harness 固定配置、标书业务插件和上游补丁 |
| `bid-writer/` | 标书编写 Skill、文档处理脚本和评审参考 |
| `infra/` | 工具链安装、运行时构建、本地启动和冒烟脚本 |
| `config/` | 试点配置 Schema；本机专用配置使用 `*.local.*` 命名 |
| `docs/` | 需求基线、实施计划和工程运行说明 |
| `research/` | 方案评估、Harness 版本与集成边界研究 |
| `evals/` | 合成评测输入、试点清单与评测说明；生成的结果保留在本机 |

`data/`、`.tools/`、`runtime/builds/` 中的运行数据、依赖、上游源码与构建清单由本机生成，不提交 Git。

## 本地开发

当前内置工具链安装脚本面向 Apple Silicon macOS，需要 Python 3.11–3.13、`uv`、`npm`、Git 和 `make`。完整安装会准备 Python 3.13、Node 24.11.1、pnpm 11.28.5 和固定版本的 Harness。

```bash
# 首次准备锁定的依赖、上游源码和构建产物，需要网络
make bootstrap

# 启动本机 API、工作台和 Worker，默认 SQLite
make dev

# 基础检查：后端业务与迁移测试、前端构建、插件类型检查
make check

# 全部后端测试，包括实际 Harness 与本机模型替身的组合测试
make test
```

工作台地址：`http://127.0.0.1:8765`。修改代码后的构建、PostgreSQL、浏览器测试和环境变量见 [工程运行说明](docs/工程运行说明.md)。运行 `make help` 查看全部命令。

## 开发入口

- [当前需求与计划索引](docs/README.md)
- [实施计划 v0.2-Harness](docs/标书Agent实施计划-v0.2-Harness.md)
- [需求基线 v0.3-Harness](docs/标书Agent需求基线-v0.3-Harness.md)
- [Agent 开发约定](AGENTS.md)

历史研究和 `bid-writer/` 保留供后续开发参考，具体能力以当前实现和实际验证结果为准。
