# Course Feedback

> Two rounds: **pre01–pre02** (setup + trace work) · **ch01–ch02** (three-layer architecture + quickstart)
> Anything marked "measured" below was produced on deepagents 0.7.8 / langchain 1.4.3 locally, by reading source or running code — not recalled.

---

## Round 1 · pre01–pre02

### What works well

**1. The lifecycle toolchain is solidly designed**

`create → info → task → doctor → dev` pulls "create a project, inspect requirements, install dependencies, check readiness, start services" into one coherent line, and each step can be run and debugged on its own. Having `doctor` block `dev` when conditions are unmet (missing keys, missing directories) is especially good — it saves far more time than "start it and see what breaks halfway".

**2. The honesty about version drift**

pre01 repeatedly says things like "commands verified on 2026-08-18 with AgentSeek 0.1.2" and "if task names differ from this article, defer to `agentseek task --list`". My experience was exactly that: the `main` template had an extra `course-check` task, and `deepagents` had moved from 0.6 to 0.7.8. Because the tutorial said this upfront, I never suspected I had installed something wrong.

**3. The Trace walkthrough in pre02 has real substance**

"162 runs, 22 model runs, 17 tool runs, slowest leaf 85.9 s, slowest tool 25.1 s" — reference numbers like these let me sanity-check my own results (I measured 46 LLM / 61 tool calls / 313 s, same order of magnitude). And the explicit instruction "do not mistake the root trace, `task` sub-agent wrappers, or middleware wrappers for the bottleneck" is exactly what stopped me from misreporting a 282-second `task` as a tool bottleneck.

**4. Security guidance is on point**

"Never write real keys into shell commands, and never use `--api-key`" — the same warning appears in the `langsmith-trace` SKILL.md, so seeing it twice makes it easy to internalise.

## Suggested additions and corrections

**1. `tavily_search` returns unbounded content (template-level issue)**

The template's `fetch_webpage_content` returns the entire `markdownify` output with no truncation. In one deep research run I accumulated **30+ `/large_tool_results/*` entries of 300 KB–1.4 MB each, 23 MB of state total**, which hard-freezes the browser's main thread on load.

Suggestion: add a default `MAX_PAGE_CHARS` (8000 worked for me) in the template's `tools.py`, or at least mention it in pre01. This is not something a student would think of on their own.

**2. Run status is not updated after an SSE disconnect (`agentseek-api` layer)**

If you refresh mid-run, or the browser freezes the tab, the SSE connection drops. The backend graph keeps running to completion, but the run status stays at `running` forever and the frontend spins indefinitely. I hit this three times and each time had to manually `POST /threads/<tid>/runs/<rid>/cancel` before the generated results became visible.

Suggestion: after the sentence "keep `agentseek dev` and the frontend page open during the run", add: "**if the page keeps spinning after an interruption, the run is stuck in `running`; cancel it and refresh — no data is lost**", and include the cancel command.

**3. No warning that background browser tabs get frozen**

This is the most common trigger for issue 2. Chrome throttles background-tab timers to once per minute and freezes long-idle tabs outright. The tutorial says "keep the page open", which makes it easy to assume "switching to another tab is fine".

Suggestion: change it to "**keep the page visible in a foreground tab during the run**; switching away can break the streaming connection".

**4. The Node/npm version guidance could be more specific**

The tutorial says "Node.js, npm current LTS". In practice Ubuntu 26.04's apt ships npm 9.2.0, and `npm install` crashes while resolving nested peer dependencies like vitest:

```
npm ERR! Cannot read properties of null (reading 'edgesOut')
```

Upgrading to npm 11 fixed it. Suggestion: add "npm ≥ 10; if you see an `edgesOut` error, upgrade npm first".

**5. pre02 assumes a coding assistant is available**

The whole chapter assumes Codex / Claude Code / Cursor. Without one (my case), steps 1–3 and 6–7 work fine, but the core practical exercises in sections 4 and 5 (have the assistant read SKILL.md and act on it) have no vehicle.

Suggestion: add a fallback: "if you have no coding assistant, read `.agents/skills/<name>/SKILL.md` directly and follow its reference files yourself, or paste the SKILL.md content into any LLM tool you use".

### Round 1 overall

The quality is higher than I expected, particularly the command explanations and the version-drift warnings — clearly written by someone with real troubleshooting experience. My five suggestions point in two directions: **template defaults should be more conservative** (truncation, caps), and **recovery paths should be in the main text, not left for students to discover**.

If I had to keep only one suggestion: **write a section on how to tell whether a frozen page means the backend died or the frontend died**, showing how to query `/state` and `/runs`. That was the part where I spent the most time and found the least external documentation.

---

## Round 2 · ch01–ch02 (Task 2)

### What works well

**1. "The three layers stack; they don't compete" is the anchor of the whole chapter**

Before reading, my mental model of LangGraph / LangChain / Deep Agents was mush — I assumed you pick one. The "workbench / hammer and saw / pre-fitted workshop" analogy plus the "they can be composed" section fixed that in one pass. Once you have that, `create_deep_agent()` → `create_agent()` → LangGraph is unsurprising.

**2. The table row "default `claude-sonnet-4-6`, but the implicit model is deprecated" is exactly right**

I read the source: `model=None` goes through `get_default_model()` → `ChatAnthropic(model_name="claude-sonnet-4-6")`, and that function carries `@deprecated(since="0.5.3", removal="1.0.0")`. **Even the deprecation versions are correct.** That level of version precision is why I trust the rest of the table.

**3. "v0.7's default base prompt is empty" is accurate to the character**

I passed `system_prompt="test"` and captured the actual system message with a spy model — **exactly the 4 characters `test`**, nothing added. If this had been written vaguely ("there's a small default prompt"), students would never know where their tokens go.

**4. "Seven file tools" is the right number**

`FilesystemMiddleware` defines eight (including `execute`), but the default binding to the model is indeed seven file tools + `task` = eight total. The course says seven, which matches real behaviour rather than copying the middleware's internal list.

**5. Managing the model name via `MODEL_NAME` is a nice touch**

Every example uses `os.environ.get("MODEL_NAME", "Qwen/...")`, so switching providers doesn't mean editing every snippet. I ran it against a DeepSeek endpoint by changing one variable.

**6. Explicitly saying "first-time readers may skip the research-assistant section"**

That permission is genuinely useful. The second half of ch02 (Tavily + `TodoListMiddleware`) is a lot for someone who just finished Hello World; the course acknowledging this beats pretending otherwise.

### Suggested additions and corrections

**1. "Default base prompt is empty" is easy to misread — add a qualifier**

Measured: with no middleware, the system message is only your own sentence (4 chars). But **with `TodoListMiddleware`, the system message becomes 1376 chars** — the extra 1372 come from the injected `## write_todos` instructions.

So "empty" means **the harness injects nothing by default**, not "the model sees no system message". Those are very different claims.

Suggested wording: **"v0.7 injects no base prompt; what you write is what the model sees. Note that middleware may append content on demand — enabling `TodoListMiddleware`, for example, adds roughly 1.4 KB of tool instructions to the system message."**

**2. `execute` is missing without explanation — students will conclude "agents can't run code"**

ch01's capability table says "virtual filesystem: 7 file tools"; ch02 never mentions `execute`. But `FilesystemMiddleware` actually defines eight tools (including `execute`); it simply **isn't bound because the default `StateBackend` cannot execute commands**.

My measured default tool list:

```
['ls', 'read_file', 'write_file', 'edit_file', 'delete', 'glob', 'grep', 'task']
```

No `execute`. If a student asks the agent to "run this snippet", it says it can't — and the course never explains why.

Suggested: add a "default / needs configuration" column to ch01's capability table, and annotate `execute` with "requires an execution-capable backend (`LocalShellBackend` or a sandbox), see ch10".

**3. The parameter table lists 3 of 18 — say so**

`print(inspect.signature(create_deep_agent))` gives **18 parameters** (`model` / `tools` / `system_prompt` / `middleware` / `subagents` / `skills` / `memory` / `permissions` / `backend` / `interrupt_on` / `response_format` / `state_schema` / `context_schema` / `checkpointer` / `store` / `debug` / `name` / `cache`).

Covering three is the right call for lesson one, but **add one sentence**: "the full signature has 15 more parameters, each the entry point for chapters 3–16; ignore them for now." Otherwise anyone who runs `help()` is lost.

**4. The middleware assembly order is never given — yet it determines "who sees the request first"**

ch01 says middleware provides capabilities and controls execution; ch02 says middleware gives the loop harness abilities. Neither states the **actual order**. From the `graph.py` docstring:

```
Base:  SkillsMiddleware(if skills) → FilesystemMiddleware → SubAgentMiddleware(if subagents)
       → SummarizationMiddleware → PatchToolCallsMiddleware → AsyncSubAgentMiddleware(if async)
User:  your middleware=[...] goes here
Tail:  profile extra → _ToolExclusionMiddleware → Anthropic/Bedrock/Fireworks PromptCaching
```

This is not a detail — it decides whether context compaction or your own middleware sees the request first. Suggested: a one-diagram addition after ch01's "who is responsible for what" table.

**5. The LangSmith section doesn't say "wrong region = silent failure"**

The course says "keep only one active endpoint", "no trailing slash", and "if no trace appears, check the region first". But it never names the failure mode:

> **The code runs perfectly, logs look normal, and the trace simply isn't in LangSmith.**

I hit this in round 1 and spent half an hour assuming the key was invalid. Suggested: state it directly — **"a region mismatch never errors; it just means you can't see the trace in the console."**

**6. "LangChain 1.0" should be "LangChain 1.x"**

`pip install "deepagents>=0.7,<0.8"` gives me **langchain 1.4.3**. The course says "LangChain 1.0 builds on LangGraph" — right major line, but minor is already at 4. Anyone searching docs for "1.0" may hit mismatches. Suggested: 1.x, or "defer to the installed version".

**7. ch01's `graph.py` link is pinned to `deepagents==0.7.1`, which conflicts with the required range**

The course requires `deepagents>=0.7,<0.8`; I have 0.7.8. But the source link points at the `deepagents%3D%3D0.7.1` tag. Students following it will find line numbers that don't match their local file (mine has `HarnessProfile`, `_excluded_middleware`, `RubricMiddleware` — all absent in 0.7.1).

Suggested: link to `main`, or note "this link is 0.7.1; your local copy may be a later 0.7.x — same function names, shifted line numbers".

**8. The "three elements" section is excellent — add one line that `Literal` locks the model's output space**

The course covers type annotations, docstrings, defaults, and shows `Literal`. It doesn't spell out what `Literal` becomes in JSON Schema. Measured:

```python
topic: Literal["general","news","finance"] = "general"
```

becomes

```json
"topic": {"default": "general", "enum": ["general","news","finance"], "type": "string"}
```

**`enum` is a hard constraint** — the model can only pick from those three, never `"tech"`. With `topic: str` that protection vanishes. For real tool authoring this buys more than type annotations alone.

Suggested: one row after the three-element table — "`Literal[...]` → `enum`, locking the model's value space".

### Round 2 overall

ch01 is conceptually dense but well-skeletoned; ch02 is a short, direct path to running code. They pair well: **first why three layers exist, then how to use the top one.**

My biggest takeaway wasn't "it runs" — it's that **every checkable claim in the course matched my local source** (default model, default prompt, default tool count, the TodoListMiddleware delta). That means the author wrote from real code, not from another blog post.

My eight suggestions cluster into three types:

1. **Boundaries left unstated** (why no `execute`, why `model` must be passed)
2. **Numbers left unstated** (middleware order, default prompt length, parameter count)
3. **Version details that drift** (1.0 vs 1.x, 0.7.1 link vs 0.7.8 local)

If I had to keep one: **put a "what you get, what you don't" table at the top of ch02** — 8 tools by default, system prompt is exactly your sentence, default backend is `StateBackend` so no command execution. With that table, students can answer every subsequent "why doesn't it…" question themselves.
