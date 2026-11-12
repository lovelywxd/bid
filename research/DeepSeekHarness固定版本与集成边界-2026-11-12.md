# DeepSeek Harness 固定版本与标书集成边界

核对日期：2026-11-12（Asia/Shanghai）。性质：官方文档、官方源码、包注册表元数据的只读核对。没有安装依赖、构建 runtime、执行上游测试、运行模型或验证真实标书。本文为[实施计划 v0.2](../docs/标书Agent实施计划-v0.2-Harness.md)提供技术依据。

## 1. 来源、版本与证据强度

本次实际执行 `git ls-remote`，官方 `HEAD` 与 `refs/heads/master` 均返回 `e8f7b93a344964de3dca1ace9e72b6e4d6de87cb`；重新取得官方源码并核对提交，而非沿用上次结论。该提交的提交者时间为 **2026-11-11T10:49:46+08:00**，根包 `@deepseek-ai/dsh-root` 为 `0.2.2-rc.2`。这只是本次观察时点的 master，不能作为未来“最新版”的永久声明。[S01]

本机 `/Users/wxd/fun/deepseek-harness`：origin 为官方 HTTPS 仓库；分支 `master`，工作区检查干净；HEAD 为 `528c682e061696f5a160f363f236ecbf53cbd006`，提交时间 2026-08-21T14:21:44+08:00。本轮只读，未 fetch、切分支或修改。实际审查使用独立临时目录中的官方快照，不将本机旧 HEAD 当作当前底座。

| 对象 | 本次核对值 | 能证明什么／不能证明什么 |
|---|---|---|
| 实施源码基线 | `e8f7b93a344964de3dca1ace9e72b6e4d6de87cb` | 本计划的接口与行为证据固定于此；实施构建还未完成 |
| 官方版本 tag | `dsh-v0.2.2-rc.2` → `ddac96760b6edf8fa0fe17cbdcf0b512f4c12b2c` | tag 与 master SHA 不同；不能用版本号假定字节一致 |
| PyPI SDK | `deepseek-harness-sdk==0.2.2rc2` | 注册表有发布；Requires-Dist 精确依赖同版本 runtime-bin [S02] |
| PyPI runtime | `deepseek-harness-runtime-bin==0.2.2rc2` | 有 macOS 14+ arm64/x86_64、manylinux_2_28 arm64/x86_64、Windows amd64 wheel；未安装启动 [S03] |
| SDK wheel SHA-256 | `ad14f1b1fccb29f7d97e5a7e0ee9dbb96d8af11292308bba66bf19a623d31899` | 来自包注册表元数据；未下载复算 |
| macOS arm64 runtime wheel SHA-256 | `76ac8fe84e6999e14a2229e20cbcaa819dc22b5bfaa40abb0fe810db8a31abc7` | 当前主机为 macOS 15.6.1 arm64，平台标签表面匹配；不是启动验证 |
| npm CLI | `@deepseek-ai/dsh@0.2.2-rc.2` | 注册表存在；返回内容无可用于确认源码对应关系的 gitHead [S04] |
| 源码 SDK pyproject | SDK/runtime 均为 `0.0.0.dev0` 模板版本 | 发布脚本从根版本写入 PEP 440 版本并改写同版本依赖，不应按源码模板安装生产包 [S05] |

对 tag 与 master 的定向 diff 检查：本报告涉及的 Python SDK/runtime、LLM 服务/DeepSeek 适配器、工具服务、基础压缩器及 sdk-minimal 配置实现未见差异；agent-loop 的该范围差异为测试文件。这是相关路径比较，不是整个发行二进制的溯源证明。

因此选择：**工程首个验证构建从固定 SHA 在隔离构建目录产生 runtime 与 SDK 配对产物**，使用官方构建/打包流程及锁文件，记录下游最小补丁和产物哈希。PyPI wheel 为可用发行候选；只有确认安装产物、插件 peer 解析、相关源码/行为对应并通过工程门后，才可作为免构建分发方式。任何差异产生新的 RuntimeBuildRevision，不能同号替换。采用 Harness 的方向已确定，这里的待验项是构建和适配能否过门。

## 2. SDK 和插件的实际调用边界

Python SDK 是 stdio 上换行分隔 JSON-RPC 的子进程客户端。`DeepSeekHarness` 延迟启动，支持 `dsh_bin`、显式 `dsh_home`、`profile`、有序 `patches`、`cwd`／`runtime_cwd`。运行 SDK wheel 不要求系统 Node；从源码构建要求 Node ≥24.9.0，根 packageManager 为 pnpm 11.28.5。当前执行环境的 Node 22 不等于满足源码构建要求，本轮没有替换系统 Node。[S01][S06]

工具扩展在 TypeScript/Cordis 层：函数插件 named-export `name/inject/apply`，以 `ctx.tools.register(defineTool(...))` 注册；`execute(args, exec)` 返回符合 output.schema 的 JSON，`output.render` 生成模型可见内容，取消信号为 `exec.signal`。注册随插件 dispose 撤销。Python SDK 文档没有提供“把 Python callable 直接内联注册为 Harness 工具”的公开接口；本计划不编造此能力。[S07]

可实现连接：Python 业务服务 → Python SDK → Harness TS 业务插件 → 仅本机业务 HTTP API。插件管理通过 `dsh plugin --profile <name> add file:<bundle>`，需要包管理环境；插件 bundle 进入 profile 包树，peer import 复用 runtime 的 Cordis。普通运行不用每次安装插件。自定义 profile 必须保留 SDK app／JSON-RPC server，错误配置直接失败，没有完整配置自动兜底。[S06]

HTTP 工具返回领域错误时，插件映射为结构化业务结果或稳定 HarnessError；传输/取消错误按工具协议处理。stdout 只留 JSON-RPC，诊断写 stderr。业务 API 校验 task token 的项目、基线、动作、租约、预算、expected_revision；模型不能通过伪造这些字段扩权。模型只提交候选，不写正式事实/正文指针或放行记录。具体服务契约见新计划第 5、6 节。

## 3. 压缩与模型请求：必须修正的默认行为

| 核对位置 | 源码事实 | 本项目适配 |
|---|---|---|
| compaction-basic/src/summarizer.ts:31—66 | 指令面向 AI coding assistant，要求 English engineering prose；会合并先前摘要 | 不加载此默认摘要策略；使用中文业务交接快照与必需原文重读 [S08] |
| compaction-basic/src/index.ts:173—195 | `agent/pre-step` 自动压缩异常捕获后记录 `continuing the turn` 并 next | 不能仅覆写 summarize 后抛错；移除默认自动处理，实际发送前另设有效性拒绝 [S09] |
| compaction-basic/src/summarizer.ts:154—181 | 摘要独立调用 `ctx.llm.stream`，purpose 为 compaction，输出额度单独配置 | 摘要若使用模型，也要单独计预算、数据范围与用量 [S08] |
| docs/architecture.md:114；agent-loop/src/agent.ts:451—567 | 重试不重新 assembly／pre-step；每个请求尝试仍进入 prepared stream | pre-step 只做提早发现；llm/stream 加每请求校验，不能只按步骤扣费 [S10] |
| llm/src/index.ts:184—207、1185—1200 | PreparedLlmCall.stream 包含 `llm/stream` waterfall；实际 adapter dispatch 在其后 | TS 插件可在每次流请求前核对 context epoch、任务取消、租约和预算许可；注册次序和真实组合需测 [S11] |
| llm-retry/README.md | 默认 normal 模式五次重试；always 可无限；直接 stream 调用单次 | 明确 normal/maxRetries=2，只允许暂时错误；禁用 always；跨会话总预算由业务账本约束 [S12] |
| llm-deepseek/src/adapter.ts:105—162 | 图片 Files 解析/失败回退；stale file id 可在同一个 stream 内再次 POST `/messages` | `llm/stream` 不等于每个 HTTP 请求；预算与数据检查必须抵达发送点 [S13] |

推荐首版使用**业务会话交接替换自动自由压缩**：当前活动在安全边界停止，保存已提交动作/候选，程序从权威记录生成 ContextSnapshot，验证后新建 session。必需条款仍按原文装配，不压缩；自由历史可归档。前置插件发现压力只发出 `CONTEXT_REBUILD_REQUIRED` 并阻止请求，不在失效请求里继续运行或递归请求摘要。控制器有界重建一次；仍超限则按完整条款组拆分或 waiting_input。不存在未验证摘要继续当前业务轮次的路径。

这条方案使用现有 SDK 的新建/恢复及业务状态，首版无需自造 Harness compaction 日志协议。以后若原位压缩确有收益，可实现 `CompactionEngine` 的 compactIfNeeded/compactNow/compactRegion 并遵守 compaction 括号及工具成对边界；另行验收，不能把它当成已经实现的首版能力。[S14]

发送点方案是**对固定上游适配器增加窄的下游 transport-admission 补丁**，在每个实际 HTTP 请求之前取得业务账本许可，之后结算或保留 unknown。重用上游序列化、流解析、工具循环和重试，不在 Python 再写一套模型网关。该补丁和 HTTP 发送审计是拟建，不是现成 Harness API。所有直发、重发、摘要、连接/能力测试、视觉及附件上传都要覆盖；不能覆盖则相应用途不启用。只文本路径可先验证，源图仍在本地查看；图片模型链路未验收时不得宣布扫描复杂材料自动核对已完成。

## 4. 权限和额外数据上传

`sdk-minimal/cordis.patch.yml` 默认挂 persistent bash/pwsh、read_image、working_directory，sandbox-policy mode 为 danger-full-access。独立 cwd 不能限制可访问路径。这是编程 profile，不是本业务沙箱。[S15]

专用业务组合从显式白名单构建，保留 SDK server、agent/loop、native tool executor、LLM、JSONL persistence/checkpoint 和必需依赖；不加载 shell、任意文件编辑、PTC run_code、子 Agent、外部 MCP、Skills 扫描、goal driver、命令管理、插件管理和自动记忆。元依赖经加载清单检查，不靠手写“只允许”提示词。最终用 `ctx.tools.guard()` 单调拒绝非本任务工具；后端 API 再拒绝越权；进程仅持临时 task token、候选目录权限和受允许的提供商凭据。[S07][S15]

新增发现：sdk-minimal 也挂载 `session-log-deepseek` 与 `plugin-package-inventory-deepseek`。前者默认把最多 8 MiB 的未接收会话日志后缀放入 `dsh_session_log` 字段，正常/摘要等请求均可能发送；它在模型 messages 之外，故不能用上下文 token 清单证明没有额外资料外发。后者默认附带 `dsh_plugin_packages`。专用组合不加载两者及其无关扩展；若保留包则明确 enabled=false，并对最终 wire payload 断言不存在。profile 升级再次验收。[S16][S17]

`Session.run()` 路由原生命令；字符串和 content-block array 都可匹配。`/permission` 能改变 session 权限，`/goal` 能启动后续自动轮次。低层 `session_prompt` 绕过 command routing，但文档说明 runtime skill recognition 仍在。采用未加载命令/skill 的专用 profile，并仅通过业务 ActionRequest 编译的任务提交；不向用户暴露任意 runtime RPC。不能只把字符串包装成数组或禁一个斜杠就声称安全。[S06]

## 5. 恢复、取消与事件

`resume_session` 恢复持久历史，修复中断末轮；丢失、不兼容或占用会话会报错，不创建替代。外部 shell、浏览器等进程不恢复。`start_session` 只是延迟 handle，不等于恢复历史。任务到 session、home、profile/build、attempt 的关联由业务库存储。[S06]

`request_timeout_seconds` 只限制协议响应；RunResult 的活动等待可以更长。观察回调失败或客户端超时不回滚活动，也不授权重试；completed 仅为终止结果种类。业务定义独立活动截止时刻，超时先停止下一步发送/工具提交，再关闭本 attempt 专用 runtime，等待退出并对账，才决定是否重建。Python 高层未提供本计划可直接使用的 Session.cancel()；SDK server 方法分派表含 initialize、session/prompt/query/resume/wait、working-directory、shutdown，不能发明 session/cancel RPC。[S06][S18]

取消实现首版选择“一次活动一个专用 runtime 进程”：标记取消、撤销 task token/预算许可、调用 SDK close→shutdown；无法有界收敛时由 worker 的子进程监管终止并回收该 attempt。必须实测清理和迟到结果 fencing；不能声称关闭进程会退回提供商费用。[S18]

持久 session/event 与瞬时 agent/assistant-stream 需分开：流 token 供展示，committed 事件及业务候选才是可对账输入。SDK 通知可能含已知后代且允许重叠；专用组合不启子 Agent，同 session 单活动，业务事件以 runtime实例+session+持久seq 去重，瞬时序号不得伪装持久提交序号。stdout 解析失败进入 execution_unknown，保存 stderr 后对账；不盲重放。[S06][S10]

## 6. 本轮结论和未验证项

源码支持 SDK/TS 插件/工具 guard/LLM 请求拦截/持久会话的适配路径；默认 profile、压缩和预算不能原样用。以上实现建议是基于源码的工程推导，尚无替身或本项目运行证据。实际选定底座是 Harness；工程门未过则修适配或提交有证据的方向调整，不暗中启用第二套完整 runtime。

尚未验证：固定源码构建、发行包二进制溯源、外部 TS bundle 真加载、wire 发送补丁、取消收敛、SDK 真实通知归集、重试计费、定向上下文交接、目标模型能力、解析/OCR、真实章节质量、整本 Word 及收益。工作区无真实招标/产品语料、批准改稿和模型试点配置，这些只阻断相应真实验证，不阻断规划。

## 7. 固定提交的一手依据

所有源码链接固定到本次审查提交。包注册表链接是本次查询入口，后续应按本文版本与哈希查询，不能再取浮动 latest。

- S01：[根包](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/package.json)、[README](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/README.md)。
- S02：[PyPI SDK 元数据](https://pypi.org/pypi/deepseek-harness-sdk/0.2.2rc2/json)。
- S03：[PyPI runtime 元数据](https://pypi.org/pypi/deepseek-harness-runtime-bin/0.2.2rc2/json)。
- S04：[npm CLI 元数据](https://registry.npmjs.org/@deepseek-ai%2Fdsh/0.2.2-rc.2)。
- S05：[源码 pyproject](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/python/sdk/pyproject.toml)、[Python 发布脚本](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/scripts/build-python-release.py#L100)。
- S06：[Python SDK 完整参考](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/python/sdk/README.md)、[runtime wheel 参考](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/python/sdk-runtime/README.md)。
- S07：[工具注册与执行](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/docs/cookbook/adding-a-tool.md)、[最终 guard](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/packages/core/tools/src/index.ts#L378)。
- S08：[默认摘要](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/packages/compaction/compaction-basic/src/summarizer.ts#L31)。
- S09：[自动压缩异常处理](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/packages/compaction/compaction-basic/src/index.ts#L173)。
- S10：[执行循环与事件](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/docs/architecture.md#L108)、[agent 请求尝试](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/packages/core/agent-loop/src/agent.ts#L451)。
- S11：[Prepared call](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/packages/llm/llm/src/index.ts#L184)、[LLM stream waterfall](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/packages/llm/llm/src/index.ts#L1185)。
- S12：[LLM 重试责任与默认值](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/packages/llm/llm-retry/README.md)、[retryPolicy schema](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/packages/llm/llm/src/retry-policy.ts)。
- S13：[DeepSeek HTTP 发送及内部重发](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/packages/llm/llm-deepseek/src/adapter.ts#L91)。
- S14：[CompactionEngine 实现约束](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/packages/compaction/compaction/README.md)。
- S15：[sdk-minimal 完整组合](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/packages/bundle/sdk-minimal/cordis.patch.yml)。
- S16：[会话日志上传](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/packages/session/session-log-deepseek/README.md)。
- S17：[插件清单上传](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/packages/llm/plugin-package-inventory-deepseek/README.md)。
- S18：[SDK server 方法及 shutdown](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/packages/sdk/server/src/server.ts#L447)、[Python close](https://github.com/deepseek-ai/deepseek-harness/blob/e8f7b93a344964de3dca1ace9e72b6e4d6de87cb/python/sdk/src/deepseek_harness/client.py#L103)。
