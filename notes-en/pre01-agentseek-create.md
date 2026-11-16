# pre01 · Bootstrapping a DeepAgents Template with the Lifecycle Workflow

> Course: <https://datawhalechina.github.io/deepagents-in-action/chapters/pre01-agentseek-create/>
> Verified on: WSL2 Ubuntu 26.04.1 / AgentSeek 0.1.6 / agentseek-api 0.2.3

## 0. What AgentSeek actually manages

| Stage | Command | Purpose |
|---|---|---|
| Create | `agentseek create` | Generate an editable project from a template |
| Inspect | `agentseek info` | Entrypoints, env requirements, tasks |
| Prepare | `agentseek task` | Run one-off tasks declared by the template |
| Check | `agentseek doctor` | Static checks: files, tools, env vars |
| Run | `agentseek dev` | Start the declared local services |

Every project contains `.agentseek/lifecycle.toml` — a **declarative manifest** of required tools, environment variables, tasks and services. AgentSeek reads it; it does not take over the application's own code.

## 1. Environment (WSL2 route)

```bash
# Windows admin PowerShell
wsl --install -d Ubuntu
wsl -l -v            # confirm VERSION = 2
wsl -d Ubuntu

# inside Linux
cd ~
sudo apt update
sudo apt install -y nodejs npm
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
uv tool install --upgrade agentseek
agentseek version     # AGENTSEEK v0.1.6
```

Points worth remembering:

- **Put projects under `~/projects`, never `/mnt/c`** — cross-filesystem (9p) small-file IO is 5–10× slower, and `node_modules` has tens of thousands of files.
- The `*` in `wsl -l -v` marks the default distribution. On this machine it was `docker-desktop` (a minimal environment registered by Docker Desktop with no `~/.bashrc` and no toolchain), so every command either needs `-d Ubuntu` or you run `wsl --set-default Ubuntu` once.
- Campus DNS resolved `github.com` to a bogus IP; a proxy was required. With `networkingMode=mirrored`, WSL can reach the Windows proxy at `127.0.0.1:7897` directly.

## 2. Create the project

```bash
mkdir -p ~/projects && cd ~/projects
agentseek create --list-templates --checkout main       # see what's available
agentseek create deepagents/research --checkout main --no-input
cd research_deepagent
```

- `--checkout main` — pull the template repo's **current main** rather than the snapshot bundled with the CLI
- `--no-input` — skip prompts, use the default project name
- **Behavioural detail**: it creates a **subdirectory** inside the current directory

## 3. Inspect the lifecycle config

```bash
agentseek info
agentseek task --list    # sync / frontend / course-check
```

Observed output:

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

> The `main` template has an extra `course-check` task that the tutorial does not mention. **Trust the actual output over the article.**

## 4. Install dependencies

```bash
agentseek task sync       # uv sync --frozen
agentseek task frontend   # npm install --prefix frontend
```

Observed:

```
sync:      Prepared 100 packages in 24.83s → Installed 119 packages in 87ms
frontend:  added 227 packages, found 0 vulnerabilities
```

Notable packages from `sync`: `agentseek-api 0.2.3`, `deepagents 0.7.8`, `langgraph 1.2.14`, and **`pylibseekdb 1.4.0.post1`** — Linux-only, which is exactly why WSL2 is mandatory on Windows.

## 5. Configure `.env`

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
```

Minimal working config (OpenAI-compatible endpoint):

```ini
AGENTSEEK_MODEL_PROVIDER=openai
AGENTSEEK_MODEL=deepseek-v4.1-flash
OPENAI_API_BASE=<your-endpoint>/v1
OPENAI_API_KEY=<your-key>
AGENTSEEK_PARALLEL_TOOL_CALLS=false
TAVILY_API_KEY=<your-tavily-key>
SEEKDB_EMBED=true
LANGSMITH_TRACING=false          # set to true for pre02
```

**Three checks before trusting a new model endpoint** (skip any one and the frontend stalls somewhere):

```bash
# 1) key works and models are listed
curl -s <endpoint>/v1/models -H "Authorization: Bearer $KEY"

# 2) it really returns tool_calls (listing models ≠ being able to reason)
curl -s <endpoint>/v1/chat/completions -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' \
  -d '{"model":"...","messages":[{"role":"user","content":"call get_weather"}],"tools":[...]}' \
  | grep finish_reason        # expect "tool_calls"

# 3) it supports streaming
# add "stream": true and look for SSE chunks starting with "data:"
```

## 6. Check and start

```bash
agentseek doctor           # all 19 checks must be ok
agentseek dev --dry-run    # print the startup plan without launching
agentseek task course-check # model-free graph test (6 passed, no tokens burned)
agentseek dev              # actually start
```

`dev` launches two processes:

```
Langgraph: uv run agentseek-api dev --port 2024
Frontend:  npm run dev              → 5174
```

Two lines in the startup log are **noise, not errors**:

```
'SHOW FULL TABLES FROM `test`' contains unsupported syntax.
    → sqlglot doesn't understand seekdb's MySQL dialect; falls back to a plain command

[sample_graphs] skipped store_memory: No module named 'graphs'
    → agentseek-api's six built-in demo graphs are absent; this project's graph lives in src/research_deepagent/
```

## 7. Run a research task

Open **`http://127.0.0.1:5174`** in a browser (not the Studio page):

```
Research what LangGraph 1.0 added vs 0.x. Cite sources.
```

Expected UI elements:

1. A todo panel appears (`TodoListMiddleware` makes the model plan first)
2. Tool cards pop up (`tavily_search` calls)
3. A nested sub-agent block (the main agent delegates via `task` to `research-agent`)
4. Todos get ticked off one by one
5. A final Markdown report with numbered citations

Observed: 3–5 minutes, 46 LLM calls, 26 search calls.

**Keep the tab in the foreground during the run** — Chrome freezes background tabs, and if the SSE stream drops the backend finishes but never tells the frontend. See [troubleshooting.md](troubleshooting.md#2-run-stuck-at-runningspinner-never-stops).

## 8. Optional: enable tracing for the next chapter

pre02 analyses this run's trace, so it must be on:

```ini
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<your-langsmith-key>
LANGSMITH_PROJECT=deepagents-course
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

**Restart `agentseek dev` afterwards** — environment variables are read at process start; `--reload` only reloads code.

## Key files

```
research_deepagent/
├── .agentseek/lifecycle.toml   declarative manifest (env/tools/paths/processes/tasks)
├── .env / .env.example
├── langgraph.json              graph entrypoint: ./src/research_deepagent/agent.py:graph
├── pyproject.toml              Python >=3.12,<3.14
├── src/research_deepagent/
│   ├── agent.py                create_deep_agent + subagent + middleware
│   ├── prompts.py              main / delegation / subagent prompts
│   └── tools.py                tavily_search + think_tool
├── frontend/                   Vite + React + @langchain/react
└── tests/                      scripted_model.py fake-model tests
```
