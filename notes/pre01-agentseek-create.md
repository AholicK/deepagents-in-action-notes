# pre01 · 用生命周期工作流启动 DeepAgents 模板

> 课程原文：<https://datawhalechina.github.io/deepagents-in-action/chapters/pre01-agentseek-create/>
> 实测环境：WSL2 Ubuntu 26.04.1 / AgentSeek 0.1.6 / agentseek-api 0.2.3

## 0. AgentSeek 到底管什么

| 阶段 | 命令 | 用途 |
|---|---|---|
| 创建 | `agentseek create` | 从模板生成可编辑项目 |
| 查看 | `agentseek info` | 项目入口、环境要求、任务 |
| 准备 | `agentseek task` | 运行模板声明的一次性任务 |
| 检查 | `agentseek doctor` | 静态检查文件/工具/环境变量 |
| 运行 | `agentseek dev` | 启动模板声明的本地进程 |

核心：每个项目有 `.agentseek/lifecycle.toml`，**声明**需要哪些工具、环境变量、任务、服务。AgentSeek 读它，但不接管应用自己的代码。

## 1. 环境准备（WSL2 路线）

```bash
# Windows 管理员 PowerShell
wsl --install -d Ubuntu
wsl -l -v            # 确认 VERSION = 2
wsl -d Ubuntu

# 进 Linux 后
cd ~
sudo apt update
sudo apt install -y nodejs npm
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
uv tool install --upgrade agentseek
agentseek version     # AGENTSEEK v0.1.6
```

要点：

- **项目放 `~/projects`，不要放 `/mnt/c`**：跨文件系统（9p）小文件 IO 慢 5–10 倍，`node_modules` 有几万文件。
- `wsl -l -v` 里的 `*` 是默认发行版。本机默认是 `docker-desktop`（Docker Desktop 注册的极简环境，没有 `~/.bashrc`、没有工具链），所以要么每条命令带 `-d Ubuntu`，要么 `wsl --set-default Ubuntu`。
- 校园网会把 `github.com` 解析成假 IP，需要代理。`networkingMode=mirrored` 下 WSL 能直接访问 Windows 的 `127.0.0.1:7897`。

## 2. 创建项目

```bash
mkdir -p ~/projects && cd ~/projects
agentseek create --list-templates --checkout main       # 先看有什么
agentseek create deepagents/research --checkout main --no-input
cd research_deepagent
```

- `--checkout main`：用模板仓库 **main 分支最新版**，而不是 CLI 内置快照
- `--no-input`：不交互，用默认项目名
- **行为要点**：在当前目录下生成**子目录**

## 3. 看生命周期配置

```bash
agentseek info        # 项目根、模板、端口、环境变量缺哪些
agentseek task --list # sync / frontend / course-check
```

实测 `info` 输出：

```
Entrypoints
  Langgraph: http://127.0.0.1:2024 (runtime: agentseek-api)
  Frontend:  http://127.0.0.1:5174 (runtime: vite)
Environment
  .env (missing)
  OPENAI_API_KEY: missing
  TAVILY_API_KEY: missing
Lifecycle Tasks
  sync: Install Python dependencies with uv.
  frontend: Install frontend dependencies.
  course-check: Run model-free course graph and artifact checks.
```

> main 分支比教程多了 `course-check` 任务。**以实际输出为准**。

## 4. 装依赖

```bash
agentseek task sync       # uv sync --frozen
agentseek task frontend   # npm install --prefix frontend
```

实测结果：

```
sync:      Prepared 100 packages in 24.83s → Installed 119 packages in 87ms
frontend:  added 227 packages, found 0 vulnerabilities
```

`sync` 关键包：`agentseek-api 0.2.3`、`deepagents 0.7.8`、`langgraph 1.2.14`、**`pylibseekdb 1.4.0.post1`**（Linux 专属，Windows 上没有 → 这就是必须 WSL 的原因）。

## 5. 配置 `.env`

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
```

最小可用配置（OpenAI 兼容端点）：

```ini
AGENTSEEK_MODEL_PROVIDER=openai
AGENTSEEK_MODEL=deepseek-v4.1-flash
OPENAI_API_BASE=<your-endpoint>/v1
OPENAI_API_KEY=<your-key>
AGENTSEEK_PARALLEL_TOOL_CALLS=false
TAVILY_API_KEY=<your-tavily-key>
SEEKDB_EMBED=true
LANGSMITH_TRACING=false          # pre02 改成 true
```

**换模型端点前三件事必验**（缺一项前端就会卡在某个环节）：

```bash
# 1) key 通 + 能列模型
curl -s <endpoint>/v1/models -H "Authorization: Bearer $KEY"

# 2) 真的回 tool_calls（关键：能列模型 ≠ 能推理）
curl -s <endpoint>/v1/chat/completions -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"...","messages":[{"role":"user","content":"call get_weather"}],"tools":[...]}' \
  | grep finish_reason        # 应该是 "tool_calls"

# 3) 支持流式
# 加 "stream": true，应看到 data: 开头的 SSE chunk
```

## 6. 检查 + 启动

```bash
agentseek doctor           # 19 项全绿才继续
agentseek dev --dry-run    # 只看启动计划，不真启动
agentseek task course-check # 假模型跑图结构（6 passed，不烧 token）
agentseek dev              # 真启动
```

`dev` 会同时起两个进程：

```
Langgraph: uv run agentseek-api dev --port 2024
Frontend:  npm run dev              → 5174
```

启动日志里两行噪音，**不是错误**：

```
'SHOW FULL TABLES FROM `test`' contains unsupported syntax.
    → sqlglot 不认 seekdb 的 MySQL 方言，回退成普通命令执行

[sample_graphs] skipped store_memory: No module named 'graphs'
    → agentseek-api 内置的 6 个 demo 图找不到，本项目图在 src/research_deepagent/
```

## 7. 跑一次研究

浏览器开 **`http://127.0.0.1:5174`**（不是 Studio 那页）：

```
Research what LangGraph 1.0 added vs 0.x. Cite sources.
```

预期界面要素：

1. todo 面板出现（`TodoListMiddleware` 让模型先列计划）
2. 工具卡片（`tavily_search` 的每次调用）
3. 子 Agent 折叠块（主 Agent 调 `task` 委派给 `research-agent`）
4. todo 逐项打勾
5. 最终 Markdown 报告，带编号引用

实测：3–5 分钟，46 次 LLM 调用，26 次搜索。

**运行期间必须保持标签在前台**——Chrome 会冻结后台标签，SSE 一断后端跑完也不通知前端。详见 [troubleshooting.md](troubleshooting.md#2-run-状态卡在-running一直转圈)。

## 8. 可选：为下一章开启 Trace

pre02 要用 Trace 分析这次研究，所以必须开：

```ini
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<your-langsmith-key>
LANGSMITH_PROJECT=deepagents-course
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

改完**必须重启 `agentseek dev`**（环境变量在进程启动时读取，`--reload` 只重载代码）。

## 关键文件

```
research_deepagent/
├── .agentseek/lifecycle.toml   声明式清单（env/tools/paths/processes/tasks）
├── .env / .env.example
├── langgraph.json              图入口：./src/research_deepagent/agent.py:graph
├── pyproject.toml              Python >=3.12,<3.14
├── src/research_deepagent/
│   ├── agent.py                create_deep_agent + 子 Agent + 中间件
│   ├── prompts.py              主 Agent / 委派 / 子 Agent 三段提示词
│   └── tools.py                tavily_search + think_tool
├── frontend/                   Vite + React + @langchain/react
└── tests/                      scripted_model.py 假模型测试
```
