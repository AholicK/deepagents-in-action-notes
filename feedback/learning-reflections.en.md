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

---

*All API keys and server addresses in this document are replaced with placeholders.*
