# 标书 Agent 开发约定

本仓库开发专用标书业务工作台。先阅读 `README.md`、`docs/README.md` 和待修改模块，需求与阶段划分以 `docs/标书Agent实施计划-v0.2-Harness.md`、`docs/标书Agent需求基线-v0.3-Harness.md` 为准。

## 代码边界

- `backend/app/` 负责业务状态、版本、权限、预算、任务调度和结果接纳；数据库结构变化使用 `backend/migrations/`。
- `frontend/src/` 负责工作台交互，业务事实来自 API。后端业务状态不能由前端自行假定完成。
- `runtime/bid-plugin/` 和 `runtime/profiles/` 负责 Harness 业务工具与组合配置。DeepSeek Harness 是唯一 Agent 执行底座，保持 `RuntimePort` 集成边界。
- 上游固定 SHA 为 `e8f7b93a344964de3dca1ace9e72b6e4d6de87cb`。上游修改记录为 `runtime/upstream-patches/` 中的补丁，通过 `infra/bootstrap.py` 应用；不能仅修改被 Git 忽略的构建目录。
- `bid-writer/` 是已有 Skill 和文档处理工具。修改前阅读该目录的 `SKILL.md` 及相应脚本，避免把历史工具的能力当作工作台已实现的功能。

## 资料与结果

- 默认开发及验证使用合成资料和本机模型替身。真实模型接入、真实资料处理需有对应任务范围，不能静默更换运行模式。
- 保留来源、数值、否定、例外和待确认项；人工锁定内容及审批边界应由业务规则约束。
- 区分工程检查、真实模型验证与标书内容验收。报告执行过的检查及其范围，不能由工程测试通过推断真实标书质量。
- 运行数据、客户资料、会话、请求日志和密钥不能提交 Git；本机数据放在 `data/`，评测产物放在 `evals/results/`。

## 开发与验证

- 使用现有 `uv.lock`、npm 锁文件和固定工具链；依赖变化同步更新对应锁文件。
- `make bootstrap` 显式安装与构建依赖；`make dev` 正常启动不下载或升级依赖。
- 运行 `make check` 做基础检查；修改 Harness、插件、契约或任务执行时运行 `make build` 和 `make test`，使清单与产物匹配。
- 修改界面交互时，在本机服务运行后执行 `make e2e`。浏览器配置见工程运行说明。
- 保留与任务无关的已有修改，避免为目录美化移动业务模块或重写历史文档。
