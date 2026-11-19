# ch01 · The Three-Layer Agent Stack and Where Deep Agents Sits

> Course: <https://datawhalechina.github.io/deepagents-in-action/chapters/ch01-agent-harness/>
> Verified against: deepagents 0.7.8 / langchain 1.4.3 / langgraph 1.2.14 / Python 3.13.18
> Tags: **[doc]** = stated in the course · **[verified]** = read from source or measured locally on 0.7.8

## TL;DR

The three layers are not competing frameworks — they are **three storeys of one building**. LangGraph keeps the agent running; LangChain standardises how you build it; Deep Agents pre-installs the file tools and sub-agent plumbing so you don't rebuild them for the fourth time. And what `create_deep_agent()` hands back is literally a compiled LangGraph graph — I verified this in one line.

---

## 1. The three layers in plain terms

**[doc]** uses the analogy: Runtime gives you the workbench and power, Framework gives you hammer and saw, Harness gives you a workshop with the tools already on the wall.

I'd add one sentence to that:

| Layer | What it actually *is* | Analogy |
|---|---|---|
| **Runtime (LangGraph)** | An **execution engine**: compiles "run A, then B, retry on error, resume from checkpoint" into a graph and ticks it forward | Chassis + engine. It moves when you press the pedal, but it doesn't know your destination |
| **Framework (LangChain)** | A set of **standard parts**: one model interface (swap providers without touching code), one tool interface (a Python function *is* a tool), the agent loop itself | Steering wheel, gearbox, dashboard |
| **Harness (Deep Agents)** | A **pre-assembled kit**: file read/write, sub-agents, context compaction, memory — everything a "serious" agent needs, already mounted | The car rolling off the line |

The point is: **they stack, they don't compete.** Use the chassis alone (hand-rolled LangGraph), bolt on the standard parts (`create_agent`), or just drive the finished car (`create_deep_agent`).

## 2. One line of code proves "Harness lands on LangGraph"

This was the claim I most wanted to test. **[doc]** says `create_deep_agent()` calls `create_agent()`, which finally executes on LangGraph.

So — what does it return?

```python
from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

agent = create_deep_agent(
    model=ChatOpenAI(model="gpt-4o-mini", api_key="sk-dummy"),
    system_prompt="test",
)
print(type(agent).__name__)      # CompiledStateGraph
print(list(agent.nodes.keys()))  # ['__start__', 'model', 'tools', 'PatchToolCallsMiddleware.before_agent']
```

**[verified]**

```
CompiledStateGraph
['__start__', 'model', 'tools', 'PatchToolCallsMiddleware.before_agent']
```

Three things at once:

1. `CompiledStateGraph` is a **LangGraph class**, not a Deep Agents one. The harness doesn't ship its own runtime — it wires up a graph and compiles it.
2. The graph has only **4 nodes**: start → call model → run tools → patch tool calls. **That is the entire skeleton of the model–tool loop**; everything else is middleware hooked onto those nodes.
3. `PatchToolCallsMiddleware` appearing *as a node name* proves middleware is **compiled into the graph**, not wrapped around it from outside.

## 3. Middleware is an onion, not a plugin

**[doc]** says middleware can provide tools, extend state, and intervene around model calls and tool execution. True, but abstract. I captured a real call stack:

```
model_node (LangChain)
 └─ FilesystemMiddleware.wrap_model_call
     └─ SubAgentMiddleware.wrap_model_call
         └─ SummarizationMiddleware.wrap_model_call
             └─ AnthropicPromptCachingMiddleware.wrap_model_call
                 └─ _execute_model_sync   ← the actual request
```

The request travels **inward**, each layer may rewrite it once (add a tool, inject prompt text, truncate history, set a cache marker), and only at the bottom does it leave for the provider. The response travels back out the same way.

This explains something that puzzled me: **how can "adding one middleware" give the model an extra tool?** Because inside `wrap_model_call` it appends one entry to the request's `tools` list. The model has no idea whether a tool is built-in or yours — to it, everything is just a JSON Schema.

**[verified]** Default assembly order (from the `create_deep_agent` docstring in `deepagents/graph.py`):

| Position | Middleware | Condition |
|---|---|---|
| Base 1 | `SkillsMiddleware` | `skills=` provided |
| Base 2 | `FilesystemMiddleware` | **always** (required, non-excludable) |
| Base 3 | `SubAgentMiddleware` | inline subagents present |
| Base 4 | `SummarizationMiddleware` | always |
| Base 5 | `PatchToolCallsMiddleware` | always |
| Base 6 | `AsyncSubAgentMiddleware` | async subagents present |
| — | **your `middleware=[...]` goes here** | — |
| Tail | `AnthropicPromptCaching` / `BedrockPromptCaching` / `FireworksPromptCaching` | installed per package, no-op for other providers |

**One rule to remember:** `FilesystemMiddleware` and `SubAgentMiddleware` are **mandatory**. The source raises `ValueError` if a harness profile tries to exclude them, because file tools and `task` are what the core features depend on.

## 4. Why a Harness layer must exist

**[doc]**'s observation: every successful agent product looks the same — Claude Code, Manus, Cursor all have filesystem access, task planning, sub-agent delegation, context management.

A more practical test I'd add:

> **If you're writing your third agent and you're writing `read_file` / `write_file` again, you need a harness.**

Conversely: one demo, one tool, one Q&A — a harness is a *cost*. It hands you 8 tools you'll never call and bills you context for them. That is exactly why v0.7 made task planning opt-in (see ch02 §6).

## 5. Context Engineering: stop stuffing prompts, hand over a filing cabinet

This is the real core of the chapter.

**Traditional (prompt stuffing):** 20 files, 50k chars, all into the system prompt. Three ways to die:

- **Overflow** — the window has a ceiling
- **Dilution** — more text, weaker attention on what matters
- **No scaling** — one more file breaks it

**Deep Agents:** give the agent a **virtual filesystem**. Read what you need with `read_file`, persist intermediate results with `write_file`, read big files in slices via `offset`/`limit`.

**[verified]** The default backend is `StateBackend`:

```python
# deepagents/graph.py
backend = backend if backend is not None else StateBackend()
```

`StateBackend` is **not a real disk** — file contents live in the LangGraph state object for that thread. Consequences:

- Upside: no directories, no permissions, nothing to clean up — ideal for development
- Limit: **it cannot execute commands.** My measurement shows `execute` is *not* bound to the model by default, precisely because `execute` needs a backend that can actually run code (local shell or sandbox)

**[doc]** lists the swappable backends: memory / local disk / database / remote sandbox / mixed routing. What that really means: **same agent code, one `backend=` line apart from toy and production.**

## 6. Competitor comparison: the only three rows that matter to me

**[doc]** gives a full table. For where I am now, three rows carry weight:

| Dimension | Why it matters today |
|---|---|
| **Model-agnostic** | I run DeepSeek/SiliconFlow now, may switch next year. A vendor-locked SDK means a rewrite |
| **Pluggable virtual filesystem** | Memory in dev, sandbox in prod — business logic untouched |
| **Python + TypeScript** | My main lane is Python; most of this industry ships TS. Keeps a door open |

Hooks, OS-level sandboxes, MCP-server mode — noise for now. Come back when needed.

## 7. Choosing a layer: three questions, top-down

**[doc]** gives a three-row table. I turned it into three questions; stop at the first "yes":

1. **Is the flow fixed?** (validate → research → human review) → **LangGraph**; write deterministic steps as nodes, drop an agent only where judgement is needed
2. **Just model + tools, but I want to control context and middleware myself?** → **LangChain `create_agent`**
3. **Neither — I want an agent that reads files, plans, and delegates on its own?** → **Deep Agents**

One line from the course deserves highlighting: *"If you don't yet have a flow that must be customised, start with Deep Agents; go deeper into LangChain or LangGraph when the abstraction runs out."*

The inverse matters more: **don't hand-roll LangGraph on day one.** I've seen tutorials build 200 lines of `StateGraph` that do less than three lines of `create_deep_agent`.

## 8. Self-test

1. What type does `create_deep_agent()` return, and which layer does that class belong to?
2. What does the "onion model" mean, and which direction does the request travel?
3. Why is `execute` **not** in the default tool list?
4. Where does `StateBackend` store files, and what can't it do?
5. Which two middlewares are mandatory, and why does the source refuse to remove them?
6. When should you **not** use a harness?

---

## Appendix: where to look in the installed package

```
.venv/lib/python3.13/site-packages/deepagents/graph.py                  # full create_deep_agent
.venv/lib/python3.13/site-packages/deepagents/middleware/filesystem.py  # the 8 file tools
.venv/lib/python3.13/site-packages/deepagents/middleware/subagents.py   # the task tool
.venv/lib/python3.13/site-packages/langchain/agents/factory.py          # create_agent / model_node
```
