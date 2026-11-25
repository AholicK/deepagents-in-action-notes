# Learning Reflections

## 1. Why WSL2 instead of native Windows

The course recommends WSL2 for Windows students. I initially tried to save time and installed everything directly in PowerShell. It failed at a very specific point: `agentseek-api` crashed on startup with `Embedded Client is not available`. Digging in, the root cause was that `pylibseekdb` only ships Linux wheels and cannot be installed on Windows.

That taught me one rule: **the keywords in an error message are more reliable than any tutorial**. Instead of hacking around it on Windows, I went back and installed WSL2 Ubuntu, which solved the whole class of problems at once — later `pylibseekdb==1.4.0.post1` installed cleanly on Linux in one shot, which was the most direct confirmation.

Along the way I finally understood a few concepts that had been fuzzy: WSL2 runs two distributions sharing a single Linux kernel, each with its own root filesystem (on my machine `docker-desktop` and `Ubuntu` sit side by side, and `uname -r` is identical); `networkingMode=mirrored` makes WSL and Windows share the loopback interface, which is why I can reach the Windows proxy at `127.0.0.1:7897` from inside Linux; and the default distribution is often the one Docker registers, with the `*` in `wsl -l -v` deciding where you land when you omit `-d`.

## 2. The AgentSeek lifecycle design

`.agentseek/lifecycle.toml` is the thing I most want to remember from this exercise. It is not a script — it is a **declarative manifest**: which commands are required, which environment variables, which files, which processes to start, and how to tell whether a service is alive. `info` reads it to display, `doctor` reads it to validate, `task` reads it to run one-off jobs, and `dev` reads it to launch services.

The practical consequence is that commands must run inside the project directory (it searches upward for `lifecycle.toml`), so running `agentseek task sync` in `~` fails with `Missing AgentSeek lifecycle spec`. It felt annoying at first, but once I understood it I appreciated the design: **environment requirements expressed as data can be validated by tooling**, which is far more reliable than a pile of scattered shell scripts.

## 3. Three "frozen page" incidents taught me diagnosis

I hit three page freezes during this project, and the root causes were completely different. This was the most valuable part of the exercise.

**First**: the page became completely unresponsive. Querying `GET /threads/<id>/state` revealed a **23 MB** state containing 30+ `/large_tool_results/*` entries, each 300 KB–1.4 MB. The root cause was that the template's `tavily_search` returned the full `markdownify` output of each page with **no length cap**, so 30 searches accumulated 20 MB and the browser's main thread died parsing it. The fix was adding `MAX_PAGE_CHARS = 8000` inside `fetch_webpage_content` — **no logic change, 5 lines**.

**Second**: the UI spun forever on "Research in progress". This time the state was only 160 KB, so size was not the issue. `GET /threads/<id>/runs` showed the run status stuck at `running` while `next: []` and all `todos` were `completed` — **the graph had finished long ago, only the state machine never closed out**. The cause was an SSE disconnect from refreshing mid-run: `agentseek-api` 0.2.3 does not mark an interrupted run as `success`. The fix is `POST .../runs/<rid>/cancel`, after which a refresh shows everything.

**Third**: I assumed "running it in a background tab should be fine" — it froze again. What I learned: **Chrome freezes background tabs** (timers drop to once per minute, and long-idle tabs get frozen outright), the SSE connection is suspended, and the frontend never receives the completion signal. The conclusion is firm: **this template requires the tab to stay in the foreground** while a research run is in progress.

The common method across all three: **do not guess from the page — query the API**. The message count in `values.messages`, the status of `values.todos`, and the `next` field from `/threads/<id>/state`, plus the status from `/threads/<id>/runs`, give you enough evidence to distinguish "still running" from "finished long ago, frontend died". This decision order saved me at least two unnecessary re-runs.

## 4. Trace analysis overturned my intuition

I assumed the bottleneck was the network or model queuing. Pulling the LangSmith trace and doing the arithmetic: **313.49 s total, of which 46 LLM calls account for 275.8 s — 88%**.

The finer detail: the slowest call took 38.78 s, but `start` to `first_token` was only **1 second** — so the bottleneck was not waiting for the first byte, it was **generation speed itself** (that call had 80,090 input tokens and produced the full final report). That directly changed the optimisation direction: raising timeouts is useless; you must cut the input or shorten the output.

The tool side was equally clear: `tavily_search` ran 26 times for 195 s total, the only tool with meaningful latency; `grep`/`read_file`/`edit_file` together accounted for 0.05 s across 27 calls and are not a problem at all. And the `task` entries that look slowest (3 calls, 282 s) are **sub-agent wrapper layers**, not tool bottlenecks — they contain their own model and tool calls, so counting them would double-count.

## 5. The real takeaway

It is not "I got an agent running". It is that I built **three habits**:

1. **Look at data before drawing conclusions** — a frozen page does not mean the service is down; two endpoints (`state` and `runs`) tell them apart.
2. **When one line fixes it, do not change ten** — a single `MAX_PAGE_CHARS` constant solved a 20 MB problem.
3. **Record the environment and versions** — `npm 9.2.0` crashed on `edgesOut` while resolving peer dependencies, and upgrading to 11 fixed it; without writing that down, I would have to rediscover it next time.

The course provides a path that works. The real skill is being able to locate which layer broke when it does not.

## 6. Task 2 broke a bad habit: stop trusting, start printing

ch01 contains one sentence I skimmed the first time: **"`create_deep_agent()` internally calls `create_agent()`, which finally executes on LangGraph."**

It reads fine, so I believed it. This time I added two lines:

```python
print(type(agent).__name__)      # CompiledStateGraph
print(list(agent.nodes.keys()))  # ['__start__', 'model', 'tools', 'PatchToolCallsMiddleware.before_agent']
```

**Two lines turned the chapter's central claim from "the docs say so" into "this is what I see".**

`CompiledStateGraph` is a LangGraph class, not a Deep Agents class — the harness doesn't ship a runtime, it configures a graph and compiles it. And there are only 4 nodes: start, call model, run tools, patch arguments. **I expected the "three-layer architecture" to be a pile of code; underneath it's four nodes.**

The reusable lesson: **any sentence of the form "internally calls X" can be verified in ten seconds with `type()` or `inspect.getsource()`.** Verify first, then keep reading — the ground feels solid.

## 7. A docstring is not written for humans

I used to think a docstring was a comment for colleagues; write it badly and nothing breaks.

ch02 killed that idea. I fed the course's `calculate` into `convert_to_openai_tool()`:

```python
def calculate(expression: str) -> float:
    """Evaluate a math expression and return the result.

    Args:
        expression: A math expression, e.g. "1 + 2 * 3".
    """
```

↓

```json
{
  "name": "calculate",
  "description": "Evaluate a math expression and return the result.",
  "parameters": {
    "properties": {
      "expression": {
        "description": "A math expression, e.g. \"1 + 2 * 3\".",
        "type": "string"
      }
    },
    "required": ["expression"]
  }
}
```

**The model never sees the function body — only this JSON.** The first docstring line becomes "when to call me"; the `Args:` block becomes "what to put in each argument"; the annotation becomes `type`; the default becomes `default` and drops out of `required`.

So what I dismissed as code hygiene is actually **writing the model's only spec sheet**. Write it vaguely and the model misuses the tool — while I blamed the model.

The biggest surprise was `Literal`:

```python
topic: Literal["general","news","finance"] = "general"
```

It becomes `"enum": ["general","news","finance"]`. **That's a hard lock** — the model can only pick from those three, never `"tech"`. With `topic: str` there is no such protection.

That reframed "constraining a model" for me: it isn't done by writing "only pick these three" in the prompt — it's done by **locking the schema**. The first relies on the model's discipline; the second is enforced by the interface.

## 8. Defaults have a price tag

ch02 says v0.7 made task planning opt-in so "short tasks don't pay a fixed cost for the planning tool and its prompt."

I skimmed that too — then measured it:

| | Without `TodoListMiddleware` | With it |
|---|---|---|
| Tool count | 8 | 9 (adds `write_todos`) |
| System message | **4 chars** | **1376 chars** |

**1372 extra characters, paid on every single request.**

That gave me a concrete feel for "context has a cost". I used to think of cost as "tokens cost money"; now I think of it as: **every middleware and every tool charges a fixed context tax on every turn.** Short tasks don't need planning tools, so don't enable them.

The same applies to "what you get by default". My measured default tools:

```
['ls', 'read_file', 'write_file', 'edit_file', 'delete', 'glob', 'grep', 'task']
```

Eight. And **no `execute`** — because the default `StateBackend` keeps files in state and cannot run commands. That explains an old confusion of mine: why some tutorials' agents run code and mine didn't. **Nothing was misconfigured; the backend simply doesn't support it.**

## 9. One thing I deliberately did not do

I **did not run the full Hello World**, and did not wire up Tavily.

Not laziness — I wanted to test a hypothesis: **can I learn exactly what the model receives without spending a cent or sending a single request?**

Yes. Write a "spy model": subclass `BaseChatModel`, copy the tool list in `bind_tools`, copy the messages in `_generate`, return a canned reply. The whole agent graph executes (all middleware included), but nothing leaves the machine.

```python
class Spy(BaseChatModel):
    @property
    def _llm_type(self): return "spy"
    def bind_tools(self, tools, **kw):
        CAP["tools"] = [t.name for t in tools]
        return self
    def _generate(self, messages, stop=None, run_manager=None, **kw):
        CAP["msgs"] = list(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="done"))])
```

I think this is worth more than one successful API round-trip: **it decouples the agent framework from the model service entirely.** For debugging any LangChain-family agent, check "what did I actually send" with this first, then spend money on the real model.

---

*All API keys and server addresses in this document are replaced with placeholders.*
