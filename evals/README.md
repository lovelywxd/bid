# 标书 Agent 评测

当前可执行检查位于：

- `backend/tests/test_invariants.py`：业务状态、版本、权限和预算等约束。
- `backend/tests/test_migrations.py`：数据库迁移往返与模型一致性。
- `backend/tests/test_pilot.py`：试点清单、对照资料一致性与验收声明约束。
- `backend/tests/test_harness_composition.py`：实际 Harness、SDK 和插件配合本机模型替身的组合场景。
- `frontend/tests/workbench.spec.ts`：工作台浏览器交互与恢复场景。

从根目录执行 `make check`、`make test` 或 `make e2e`；前置条件见 `docs/工程运行说明.md`。

`fixtures/` 和 `manifests/` 收录合成工程输入与试点清单，`labels/` 说明人工标签准备要求。可执行 `backend/.venv/bin/python infra/check_pilot.py` 校验默认清单和资料哈希，输出准备状态；该命令不会运行模型。

生成证据保存在 `results/`，由 Git 忽略，可能包含会话、请求和资料内容。可共享的评测结论应先脱敏，再整理到 `docs/`。当前工程合成检查不等同于真实模型、真实资料或标书质量验收。
