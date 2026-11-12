# 固定上游补丁

基线 `e8f7b93a344964de3dca1ace9e72b6e4d6de87cb`（0.2.2-rc.2）。

`0001-send-admission.patch` 只改 DeepSeek Messages adapter 的实际发送点及新增许可函数：正文序列化后、每次 fetch 前申请一次不可复用许可；关闭图片/Files，仅允许指定本机替身端点。重试和工具循环仍由 Harness 执行。许可服务只计账和拒绝，不转发请求。

运行 `uv run --project backend python infra/bootstrap.py --install --build-harness` 可在本项目隔离目录准备、应用补丁、运行官方构建及检查。不会触碰 `/Users/wxd/fun/deepseek-harness`。正常 `infra/dev.py` 不下载或构建。已构建产物和 SDK 源码由 `runtime/builds/active.json` 固定。

本补丁尚未上游发布；固定源码 SDK 与本机构建 CLI 配对使用，不声明与 PyPI wheel 等价。第三方依赖按官方锁文件安装，清单不逐一校验整个 node_modules。
