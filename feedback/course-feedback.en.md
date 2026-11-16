# Course Feedback

## What works well

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

## Overall

The quality is higher than I expected, particularly the command explanations and the version-drift warnings — clearly written by someone with real troubleshooting experience. My five suggestions point in two directions: **template defaults should be more conservative** (truncation, caps), and **recovery paths should be in the main text, not left for students to discover**.

If I had to keep only one suggestion: **write a section on how to tell whether a frozen page means the backend died or the frontend died**, showing how to query `/state` and `/runs`. That was the part where I spent the most time and found the least external documentation.
