# pre02 · Installing Development Skills for a Coding Assistant + Trace Workout

> Course: <https://datawhalechina.github.io/deepagents-in-action/chapters/pre02-agentseek-skills/>
> Prerequisite: pre01 done, and `LANGSMITH_TRACING=true` in `.env`

## Two kinds of skills (get this straight first)

| Type | Consumer | Installed via | Covered here |
|---|---|---|---|
| **Coding-assistant development skill** | Codex / Claude Code / Cursor | `npx skills add ...` | ✅ |
| **DeepAgents runtime skill** | the Deep Agent you build | `create_deep_agent(skills=[...])` | ❌ (chapter 7) |

Both use `SKILL.md`, but they serve completely different consumers.

## 1. List available skills

```bash
node --version && npm --version
cd ~/projects/research_deepagent
npx skills add ob-labs/agentseek --list
```

Observed — four skills:

```
github-repo-cards
langchain-dev-guide     ← install
langsmith-trace         ← install
documentation-writer
```

## 2. Install into the current project

```bash
npx skills add ob-labs/agentseek \
  --skill langchain-dev-guide \
  --skill langsmith-trace \
  --agent cursor --yes
```

`--agent` decides the target directory:

| Assistant | Project-level | Global |
|---|---|---|
| Codex | `.agents/skills/` | `~/.agents/skills/` |
| Claude Code | `.claude/skills/` | `~/.claude/skills/` |
| Cursor | `.agents/skills/` | `~/.cursor/skills/` |

The installer also prints a security assessment:

```
langchain-dev-guide  Safe / 0 alerts / Low Risk
langsmith-trace      Safe / 0 alerts / Med Risk
```

**You can install without having the assistant CLI** — the files still land in `.agents/skills/`; `npx skills list` just reports `Agents: not linked`.

## 3. Verify

```bash
npx skills list
find .agents/skills -type f | sort
```

File counts observed:

```
langchain-dev-guide: 14 (SKILL.md + 10 reference/*.md + template/chat_model.py)
langsmith-trace:      2 (SKILL.md + reference/cli-commands.md)
```

## 4. Use langchain-dev-guide to audit the model config

The course prompt:

> Use langchain-dev-guide to check this deepagents/research project's model configuration. Verify the environment variables and explain the compatibility boundaries for Tool Call, reasoning_content, etc.

**Without a coding assistant**: read `reference/deepagents.md` and `reference/model-integration.md` directly.

### Actual configuration

| Item | Value | Source |
|---|---|---|
| `AGENTSEEK_MODEL_PROVIDER` | `openai` | `.env` |
| `AGENTSEEK_MODEL` | `deepseek-v4.1-flash` | `.env` |
| Code path | `init_chat_model(...)` → `ChatOpenAI` | `agent.py:133–152` |

### Four boundaries the skill documents

**① `reasoning_content` is silently dropped**

> `_create_chat_result` and `_convert_chunk_to_generation_chunk` don't recognise the field.

Current risk: **not triggered**. Measured `completion_tokens_details.reasoning_tokens: 0` and `content` carries normal text. Switching to a real reasoning model (thinking mode on) means the frontend will not see the thinking process.

**② Multi-turn reasoning context is broken**

> `_get_request_payload` does not handle `additional_kwargs["reasoning_content"]`, so the previous turn's reasoning chain is lost.

Same trigger condition as ①.

**③ An empty `tools: []` triggers provider 400s**

Low risk here: both tools (`tavily_search`, `think_tool`) are always bound.

**④ `invalid_tool_calls` (weak models emitting malformed JSON)**

Already covered by deepagents' built-in `PatchToolCallsMiddleware` — the first node in the Studio graph, `PatchToolCallsMiddleware.before_agent`. **No need for `ToolCallRepairMiddleware`.**

### Conclusion

The current setup (`deepseek-v4.1-flash` + `parallel_tool_calls=false` + 300s chunk timeout) is safe: three of the four boundaries don't trigger, and the fourth is covered by middleware.

---

## 5. langsmith-trace workout

### 5.1 Install the CLI and authenticate

```bash
curl -fsSL https://cli.langsmith.com/install.sh | sh
command -v langsmith && langsmith --version    # 0.4.0

# load credentials from .env (never pass --api-key: it leaks into shell history)
cd ~/projects/research_deepagent
set -a; . ./.env; set +a

langsmith --format pretty project list
```

```
 NAME                 ID                                    RUNS  ERROR RATE  LAST ACTIVE
 deepagents-course    41f00083-df9f-43ab-90c8-0c24174ffb77   1    100.0%      2026-11-16 12:54
```

> The 100% error rate belongs to the failed attempt after the model tunnel dropped; harmless.

### 5.2 Find the trace

```bash
langsmith trace list --project deepagents-course --name research \
  --include-metadata --limit 5
```

In this project the trace name is `LangGraph`, not `research`, so:

```bash
langsmith trace list --project deepagents-course --limit 5
# trace_id: 01a1e46c-3547-7b10-bcca-4a9c7986215c

langsmith trace get 01a1e46c-3547-7b10-bcca-4a9c7986215c \
  --project deepagents-course --include-metadata
```

The output is the full span tree (see [../trace/trace-analysis.md](../trace/trace-analysis.md)).

### 5.3 Analyse bottlenecks by run type

```bash
TID=01a1e46c-3547-7b10-bcca-4a9c7986215c

langsmith run list --trace-ids $TID --project deepagents-course \
  --run-type llm --include-metadata --limit 100 --format json > llm.json

langsmith run list --trace-ids $TID --project deepagents-course \
  --run-type tool --include-metadata --limit 100 --format json > tool.json
```

Aggregate in Python (**always exclude `task`**):

```python
import json
llm = json.load(open("llm.json"))
tool = json.load(open("tool.json"))
dur = lambda r: r.get("duration_ms") or 0

print("LLM:", len(llm), "total", sum(dur(r) for r in llm)/1000, "s")
for r in sorted(llm, key=dur, reverse=True)[:5]:
    print(f"  {dur(r)/1000:.2f}s", r.get("token_usage", {}).get("total_tokens"), r["run_id"])

real = [r for r in tool if r.get("name") != "task"]     # ← critical: exclude sub-agent wrappers
for r in sorted(real, key=dur, reverse=True)[:5]:
    print(f"  {dur(r)/1000:.2f}s", r.get("name"), r["run_id"])
```

Results: [../trace/trace-analysis.md](../trace/trace-analysis.md).

### 5.4 Check the analysis

| Check | Standard | This project |
|---|---|---|
| Trace selection | most recent completed research trace | ✅ 313.49s |
| Hierarchy | root / sub-agent / model / tool separated | ✅ |
| Model bottleneck | slowest `run_type=llm` leaf | ✅ 38.78s / 80,090 tokens |
| Tool bottleneck | slowest real tool (excluding `task`) | ✅ tavily_search 11.23s |
| Evidence | run_id, duration, status, IO inspection | ✅ |
| Recommendations | mapped to evidence | ✅ |

## 6. Update skills

```bash
npx skills update -p        # project-level
npx skills update -g        # global (if installed globally)
npx skills list
```

## 7. Optional: global install

```bash
npx skills add ob-labs/agentseek \
  --skill langchain-dev-guide --skill langsmith-trace --global
```

## Remove

```bash
npx skills remove langchain-dev-guide langsmith-trace --yes
```
