# Python 学习 · 代码实验室

从原始 `Python 学习.html` 拆分出的本机应用。原文件保持不变，仍可作为旧版参考；新版入口是 **http://127.0.0.1:5173**，不再双击 HTML 启动。

## 启动

当前工作区已安装依赖。双击 **启动.command**，或在项目目录运行：

```sh
python3 dev.py
```

打开 http://127.0.0.1:5173。终端按 Ctrl+C 同时关闭两个服务。端口已被占用时，启动器会提示，不会结束其他进程。

新机器需要 Python 3.9+（推荐 3.11+）、Node.js 20.19+ 或 22.12+、npm，以及 macOS/Linux：

```sh
./setup.sh
python3 dev.py
```

首次安装需要网络。前端依赖已打包，不再依赖运行时的 Tailwind、Lucide、Skulpt CDN。普通 Python 练习不需要网络，AI 请求需要网络和对应服务商的密钥。

## 前后端分离

```text
浏览器 → Vite 前端 :5173 → /api 代理 → FastAPI 后端 :8000
                                          ├─ SQLite：脚本、设置、聊天、提供商
                                          ├─ 本机 Python 子进程：执行代码
                                          └─ HTTP：模型服务商 API
```

- `frontend/index.html`：界面结构；`frontend/src/style.css`：主题与布局。
- `frontend/src/main.js`：编辑器、脚本、设置、终端、聊天交互。
- `frontend/src/api.js`：统一 API 调用；`i18n.js`：中英界面文案。
- `backend/app.py`：REST API、输入校验、本机请求保护。
- `backend/store.py`：SQLite 和密钥加密。
- `backend/runner.py`、`worker.py`：独立执行进程、输入输出和资源限制。
- `backend/ai.py`：三种模型协议适配。
- `backend/tests/`：接口、持久化、真实执行、模型协议与异常测试。

可以分别运行：

```sh
# 终端一：后端（只能启动一个 worker）
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000

# 终端二：前端
npm run dev --prefix frontend
```

API 文档：http://127.0.0.1:8000/docs 。受保护接口需要 `X-Lab-Token` 请求头；本机客户端可从 `/api/session` 获取当前进程的 token。前端自动管理该 token，并在后端重启后重新获取。

前端构建与预览：

```sh
npm run build --prefix frontend
npm run preview --prefix frontend
```

预览地址：http://127.0.0.1:4173，仍需启动后端。后端不托管前端文件。开发/预览代理可以通过 `LAB_API_URL` 指定后端地址；默认配置只接受本机前端来源。

## 已实现

- 脚本新建、重命名、搜索、切换、删除，500ms 防抖自动保存。
- SQLite 持久化；保存失败保留页面内容；多窗口版本冲突返回 409，避免静默覆盖。保存状态可点击重试，⌘/Ctrl+S 也可保存。尚未保存时离开页面会提示。
- `.py` 导入/导出、多脚本 JSON 导入/导出。导入新增脚本，文件总量上限 8MB、最多 1000 个脚本、每个脚本最多 20 万字符。
- Python 语法高亮、行号、Tab/Shift+Tab 缩进、回车自动缩进、⌘/Ctrl+Enter 运行、⌘/Ctrl+K 搜索。
- 使用启动后端的 Python 解释器真实执行，支持标准库和该虚拟环境已安装的包。运行工作目录为临时目录，执行结束清理；不保留生成的文件。
- 250ms 轮询输出；支持 `input()` 逐行输入、EOF、停止，2–60 秒超时，输出上限 128KB，一次只运行一个脚本。刷新页面可恢复正在运行的进程；最近 30 次运行暂存在后端内存，后端重启清空。
- AI 提供商增删改、获取模型目录、手动编辑模型 ID、选择当前提供商/模型。
- OpenAI Chat Completions、OpenAI Responses、Anthropic Messages 三种协议；兼容服务商按其实际协议选择。
- AI 对话按脚本存储，附带当前代码、多轮上下文、报错解释、Markdown 显示、代码复制/填入、清空对话。
- 中英文、浅色/深色/跟随系统、字号、缩进、执行超时均可设置并持久化；字号影响编辑器和会话。
- 四组练习示例：变量、循环、交互输入、函数与异常。

AI 当前采用完整回复模式，不做 token 流式输出。每次请求携带最近最多 20 条历史消息、约 10 万字符历史上下文，超出部分截断。失败请求不写入聊天记录，界面恢复本次问题供重试；输出错误不会泄露上游响应中的密钥。

## 配置模型

在「设置 → 模型提供商」编辑默认 DeepSeek，填写自己的密钥并保存。也可添加其他服务商：

| 协议 | API 根地址示例 | 后端请求路径 |
| --- | --- | --- |
| OpenAI Chat Completions | `https://api.deepseek.com/v1` 或兼容地址 | `/chat/completions` |
| OpenAI Responses | `https://api.openai.com/v1` | `/responses` |
| Anthropic Messages | `https://api.anthropic.com/v1` | `/messages` |

填写根地址，不要重复填写末尾请求路径。远程地址必须使用 HTTPS，本机模型可使用 `http://127.0.0.1:端口/v1` 且可不填密钥。保存后点「获取模型」调用服务商 `/models`；服务商不提供此接口时可在编辑页手动填写模型 ID。获取目录取响应第一页，最多 500 个；未出现在目录里的 ID 仍可直接填入会话顶部使用。

密钥只通过本机请求写入后端，数据库内为 Fernet 密文，读取 API 只返回 `has_key`。编辑时留空保留密钥，勾选「移除」才会清除。聊天和附带的代码会发送给所选服务商。

协议实现参考：[OpenAI 文本生成文档](https://developers.openai.com/api/docs/guides/text)、[Anthropic 模型列表文档](https://platform.claude.com/docs/en/api/models/list)。真实服务可用性、模型权限及费用取决于你的服务商账号；测试未使用真实密钥或产生模型调用费用。

## 数据与旧版迁移

默认数据库：`backend/data/lab.sqlite3`。本机加密密钥：`backend/data/.key`。两者都已加入忽略规则，不要提交到代码仓库。完整迁移/备份时，**先停止后端，再复制整个 `backend/data` 目录**；必须保留 `.key`，否则已存的服务商密钥无法解密。可用 `LAB_DATA_DIR` 环境变量指定其他数据目录。

界面里的 JSON 备份只包含脚本，不包含聊天、设置、密钥。导出会包含当前页面尚未保存的脚本内容，便于保存冲突或离线时抢救编辑。

旧版脚本存在原浏览器的 localStorage 中。若旧版和新版运行于同一来源，新版会提示导入；直接通过 `file://` 打开的旧版与新版地址不同，浏览器不会允许新版直接读取旧版数据。

对于 `file://` 旧版：在原浏览器打开原 HTML，打开开发者工具 Console，执行下面这段本地导出代码，然后在新版「设置 → 数据 → 导入脚本」选择下载的 JSON。它只读取旧版脚本，不读取提供商密钥，也不会修改旧数据。

```js
const legacy = localStorage.getItem('macos_notes_python_storage_v4') || '[]';
const blobUrl = URL.createObjectURL(new Blob([legacy], {type: 'application/json'}));
const link = document.createElement('a');
link.href = blobUrl;
link.download = 'python-legacy-notes.json';
link.click();
setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
```

## 执行边界

这是单用户本机学习工具，服务默认只监听 `127.0.0.1`，带来源/Host 校验和会话 token。执行进程使用临时目录、隔离 Python 启动参数、最小环境变量、进程组终止、CPU/文件/输出限制；Linux 另有 512MB 虚拟内存限制，macOS 不提供同等内存上限。

**这些限制不是安全沙箱。代码仍拥有当前系统用户的文件与网络权限。** 只运行你信任的代码，不要将此版本直接暴露到局域网或公网。多用户部署需要额外的身份认证，以及容器/虚拟机级别的执行隔离。当前只支持 macOS/Linux，不支持 Windows 进程控制。

## 验证

```sh
.venv/bin/python -m pytest backend/tests -q
npm run build --prefix frontend
```

自动化测试使用临时数据库，覆盖脚本持久化与版本冲突、设置校验、导入导出、密钥加密、来源/Host 防护、真实 Python 执行与异常、交互输入/EOF、超时/停止/输出上限、三种 AI 协议和上游错误。AI 测试通过 mock transport 验证请求与响应，不访问真实服务。

可选的本地 AI 界面测试服务（不会随正常应用启动）：

```sh
.venv/bin/python -m uvicorn backend.tests.mock_provider:app --host 127.0.0.1 --port 18080
```

在「设置 → 模型」新增临时提供商，使用 `http://127.0.0.1:18080/v1`、Chat Completions 协议，不填密钥。获取模型后选择 `fixture-python-tutor`，即可验证会话和代码块操作。此服务只返回固定测试文本，不是真实模型。

当前验证环境的精确 Python 依赖记录在 `backend/requirements.lock.txt`；前端依赖由 `frontend/package-lock.json` 锁定。

## 原始界面与管理入口

主界面和设置窗口沿用原始 HTML 的布局。新增的标题栏、连接状态、编辑器状态栏、AI 欢迎内容和独立模型栏已移除。

右键点击脚本、左下角「设置」或顶部 AI 图标，选择「脚本与模型管理」，可重命名/删除/导入导出脚本、选择当前提供商与模型、清空对话、调整缩进和超时、创建练习示例。原来的「设置 → 模型 → 编辑」可保存密钥、获取/编辑模型目录、删除提供商。停止和输入框仅在运行时显示。
