# DeepAgents in Action · Study Notes

A complete record of following the [datawhalechina/deepagents-in-action](https://github.com/datawhalechina/deepagents-in-action) course, **pre01–pre02 + ch01–ch02**: environment setup, command breakdowns, troubleshooting, trace bottleneck analysis, and source-level verification of the three-layer architecture.

> 中文版: [README.md](README.md)

## Environment

| Item | Version |
|---|---|
| Host | Windows 11 + WSL2 Ubuntu 26.04.1 LTS |
| Python (project) | 3.13.18 (managed by uv; system Python 3.14.4 untouched) |
| Node / npm | 22.22.1 / **11.x** (apt ships 9.2.0, which has a bug — see pitfall #3) |
| uv | 0.13.8 |
| AgentSeek | 0.1.6 (scaffolding) / agentseek-api 0.2.3 (runtime) |
| deepagents / langchain / langgraph | 0.7.8 / 1.4.3 / 1.2.14 |
| langchain-core / langchain-openai / langsmith | 1.6.7 / 1.6.7 / 0.14.4 |
| Model | OpenAI-compatible endpoint + `deepseek-v4.1-flash` |
| Search | Tavily (free tier) |
| Tracing | LangSmith project `deepagents-course` |

**Why WSL2 instead of native Windows**: `pylibseekdb` (the embedded seekdb client) only ships Linux wheels. On Windows, `agentseek-api` crashes at startup with `Embedded Client is not available`.

## Layout

```
├── notes/                            Chinese notes
│   ├── pre01-agentseek-create.md
│   ├── pre02-agentseek-skills.md
│   ├── ch01-agent-harness.md         three-layer stack + source-level checks
│   ├── ch02-quickstart.md            first agent + schema translation measured
│   └── troubleshooting.md
├── notes-en/                         English notes
├── trace/
│   └── trace-analysis.md             bottleneck analysis of the 313s trace
├── feedback/
│   ├── 学习心得.md / learning-reflections.en.md
│   └── 课程内容反馈.md / course-feedback.en.md
└── assets/
```

## Five hard findings from ch01–ch02 (measured, not quoted)

| Finding | Evidence |
|---|---|
| `create_deep_agent()` returns **LangGraph's `CompiledStateGraph`** | `type(agent).__name__`; only 4 nodes in the graph |
| Default binding is **8 tools**: 7 file tools + `task`, **no `execute`** | Spy model capturing `bind_tools` arguments |
| Default system prompt is **exactly your sentence** (`"test"` → 4 chars received) | Spy model capturing `_generate` messages |
| Adding `TodoListMiddleware` = **+1 tool, +1372 chars of system** | before/after: 4 → 1376 |
| The three elements compile to JSON Schema; `Literal` → `enum` (hard lock) | `convert_to_openai_tool()` output |

## Outcomes

- Completed **3 full deep-research runs**, producing 3 reports (11k–13k Chinese characters each, all with numbered citations)
- LangSmith trace: **313.49 s / 46 LLM calls / 61 tool calls**
- Found and fixed **2 genuine template defects** (state bloat, run status not reaped)
- Source-verified **6 checkable claims** from ch01–ch02 against local 0.7.8 — **all consistent** (default model / default prompt / default tool count / middleware order / parameter count / why `execute` is absent)

## Four pitfalls at a glance

| Symptom | Root cause | Fix |
|---|---|---|
| Page completely frozen | `tavily_search` has no length cap → 23 MB state | `MAX_PAGE_CHARS = 8000` |
| Spins forever on "Research in progress" | Run stuck at `running` after SSE drop | `POST /threads/<tid>/runs/<rid>/cancel` |
| Freezes again (this time in a background tab) | Chrome freezes background tabs, SSE suspended | Keep the tab in the foreground |
| `npm ERR! ... 'edgesOut'` | npm 9.2.0 peer-dependency resolver bug | Upgrade to npm 11 |

Full diagnosis in [notes-en/troubleshooting.md](notes-en/troubleshooting.md).

## Three commands to tell whether it's really stuck

Do not guess from the page — query the API:

```bash
# 1. Is the server alive?
curl -s http://127.0.0.1:2024/ok

# 2. Has the graph finished? (empty next = done)
curl -s http://127.0.0.1:2024/threads/<tid>/state \
  | python3 -c "import sys,json; d=json.load(sys.stdin)['values']; print('msgs',len(d['messages']),'next',d.get('next'))"

# 3. Has the run been reaped?
curl -s http://127.0.0.1:2024/threads/<tid>/runs \
  | python3 -c "import sys,json; [print(r['status'], r['run_id'][:20]) for r in json.load(sys.stdin)]"
```

Decision table:

| `next` | run status | Conclusion |
|---|---|---|
| non-empty | `running` | genuinely running, wait |
| `[]` | `running` | **finished but not reaped** → cancel + refresh |
| `[]` | `success`/`error` | frontend problem |

## Notes

- All API keys and server addresses are placeholders; no real credentials are included.
- Course: <https://datawhalechina.github.io/deepagents-in-action/>

## License

MIT
