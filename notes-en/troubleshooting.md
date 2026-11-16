# Troubleshooting Log: Four Real Pitfalls

Every entry below was reproduced on a real machine, with symptom, diagnosis, root cause, fix and prevention.

---

## 1. Page completely frozen: thread state bloated to 23 MB

### Symptom

The browser becomes unresponsive — the input box cannot be clicked, switching tabs lags. But:

- `curl http://127.0.0.1:2024/ok` → `200`
- the backend process still burns CPU

### Diagnosis

Rule out "backend died": `/ok` is 200, the service is alive. Then inspect the thread state:

```bash
curl -s "http://127.0.0.1:2024/threads/<tid>/state" -o state.json
ls -lh state.json      # 23M ← this is the problem
```

Break down the `files` field:

```python
import json
d = json.load(open("state.json"))
files = d["values"]["files"]
for n, k in sorted(((len(str(v)), k) for k, v in files.items()), reverse=True)[:5]:
    print(f"{n:>10,}", k)
```

Output:

```
1,468,190  /large_tool_results/call_01_ET_0LP6V7pRkEVMKuyjFepP8859
1,046,xxx  /large_tool_results/call_01_IGo15rWB3pMGnxPJobgn3369
   ...
   523,564  /conversation_history/session_xxx.md
    13,231  /final_report.md          ← the report itself is tiny
```

**30+ `/large_tool_results/*` entries of 300 KB–1.4 MB each, 20+ MB total.**

### Root cause

The template's `tools.py`:

```python
response = httpx.get(url, ...)
response.raise_for_status()
return markdownify(response.text)      # ← whole page to markdown, no length cap
```

`tavily_search` does this for every result (`max_results=3`), so a single search can return three full web pages. The sub-agents run 10+ searches in parallel → 30 searches → 20 MB.

DeepAgents spills oversized tool results into `values.files['/large_tool_results/*']`, and **the frontend downloads the entire thread state on load** → the browser's main thread dies parsing 23 MB of JSON.

### Fix (5 lines, no logic change)

In `src/research_deepagent/tools.py`:

```python
# after tavily_client = TavilyClient()
MAX_PAGE_CHARS = 8000

# inside fetch_webpage_content
def fetch_webpage_content(url: str, timeout: float = 15.0) -> str:
    ...
    response.raise_for_status()
    text = markdownify(response.text)
    if len(text) > MAX_PAGE_CHARS:
        omitted = len(text) - MAX_PAGE_CHARS
        text = text[:MAX_PAGE_CHARS] + f"\n\n[... truncated {omitted} chars ...]"
    return text
```

**The truncation must live inside `fetch_webpage_content`** — both the main agent and the sub-agent get page text from there, so one change covers everything.

Verify:

```bash
.venv/bin/python -c "import ast; ast.parse(open('src/research_deepagent/tools.py').read())"
.venv/bin/python -c "import sys; sys.path.insert(0,'src'); from research_deepagent.tools import MAX_PAGE_CHARS; print(MAX_PAGE_CHARS)"
```

`agentseek-api` uses `StatReload` and reloads automatically (`Detected file changes, reloading` in the terminal).

### Effect

| | Before | After |
|---|---|---|
| One search | 3 full pages (up to 1.4 MB) | 3 × 8000 = 24 KB |
| 30 searches | ~20 MB | ~720 KB |
| New thread state | 23 MB | **160 KB** |
| Frontend | frozen | fine |

### Prevention

- Always open new sessions at the bare root `http://127.0.0.1:5174`; opening an old `?thread=` URL re-triggers the freeze.
- The bloated state is already persisted in seekdb and **cannot be salvaged**.

---

## 2. Run stuck at `running`: spinner never stops

### Symptom

The page is not frozen, but it shows **"Research in progress"** forever and the input stays disabled.

### Diagnosis

```bash
TID=<thread-id>

# 1) is the data complete?
curl -s "http://127.0.0.1:2024/threads/$TID/state" | python3 -c "
import sys, json
d = json.load(sys.stdin)
v = d.get('values', {})
print('messages:', len(v.get('messages', [])))
print('todos:', [(t['status'], t['content'][:20]) for t in (v.get('todos') or [])])
print('next:', d.get('next'))
"
```

```
messages: 35
todos: [('completed', ...) × 4]
next: []                            ← the graph has finished
```

```bash
# 2) what does the run say?
curl -s "http://127.0.0.1:2024/threads/$TID/runs" | python3 -c "
import sys, json
for r in json.load(sys.stdin):
    print(r['status'], r['run_id'][:20], r.get('created_at'), r.get('updated_at'))
"
```

```
running  08d13b78-0e1c-4db7-a   2026-11-16T02:06:32.821   2026-11-16T02:06:32.862
                                  ↑ frozen 40 ms after creation
```

**Contradiction: `next: []` (graph finished) but `status: running` (never reaped).**

### Root cause

A defect in **`agentseek-api` 0.2.3**: when the SSE client disconnects, the backend graph runs to completion but the run is never marked `success`. The frontend's `useStream` sees `status=running`, keeps `isLoading=true`, and waits forever for a signal that will never arrive.

**Trigger**: refreshing mid-run, closing the tab, or Chrome freezing the tab (see pitfall #3).

### Fix

```bash
curl -X POST "http://127.0.0.1:2024/threads/<tid>/runs/<rid>/cancel"
```

After the status becomes `error`, refresh the page — **everything already generated is visible** (no data loss).

Export the artefact:

```bash
curl -s "http://127.0.0.1:2024/threads/<tid>/state" -o st.json
python3 -c "
import json
rep = json.load(open('st.json'))['values']['files']['/final_report.md']['content']
open('report.md','w',encoding='utf-8').write(rep)
print('saved', len(rep), 'chars')
"
```

### Do not restart the service first

Cancel first. Restarting discards in-memory sessions and does not fix the root cause.

The only case that warrants a restart: `ps` shows `runtime_entrypoint` sustained at 40%+ CPU while all runs are terminal — the runtime is spinning (observed after a session with a huge state).

Confirm the ports are clear before restarting:

```bash
ss -lntp | grep -E ':2024|:5174' || echo "ports clear"
```

---

## 3. It freezes in a background tab too: Chrome throttles background tabs

### Symptom

Mid-run you switch to another tab to read something. When you come back it is spinning again — **without any refresh**.

### Root cause

Three layers stacked:

1. The frontend's `useStream` depends on a **long-lived SSE connection**
2. **Chrome throttles background tabs**: timers drop to once per minute, and long-idle tabs get frozen outright, suspending network connections
3. When SSE drops the backend graph keeps running (it doesn't depend on the connection), but `agentseek-api` never updates the run status → stuck at `running` (pitfall #2)

### Conclusion

**While a deep-research run is in progress, the page must stay in a visible foreground tab.**

"Keeping the page open" is not the same as "keeping it in the foreground".

### Mitigations

| Approach | Effect |
|---|---|
| Don't switch away during the run | most reliable |
| `chrome://flags/#disable-background-timer-throttling` + `#disable-backgrounding-occluded-windows` → Enabled | helps, not guaranteed |
| Cancel + refresh when stuck | fallback |

---

## 4. `npm ERR! Cannot read properties of null (reading 'edgesOut')`

### Symptom

`agentseek task frontend` fails immediately:

```
npm ERR! Cannot read properties of null (reading 'edgesOut')
npm ERR! A complete log of this run can be found in:
npm ERR!     /home/<user>/.npm/_logs/...-debug-0.log
```

### Diagnosis

Look at the key lines in the log:

```bash
tail -35 ~/.npm/_logs/<log>.log | grep -E "at |npm "
```

```
at [loadPeerSet] (/usr/share/nodejs/@npmcli/arborist/lib/arborist/build-ideal-tree.js:1304)
at async Install.exec (/usr/share/nodejs/npm/lib/commands/install.js:146)
npm v9.2.0
timing ... idealTree:node_modules/vitest
```

Key facts:

- `/usr/share/nodejs/` — the **Ubuntu/debian packaging path**; apt splits npm into dozens of separate debs
- `loadPeerSet` crashes resolving **vitest's** peer dependencies
- npm version **9.2.0** (early 2023)

### Root cause

npm 9.2.0's arborist reads null in some nested peer-dependency graphs. Known bug, fixed in npm 10+.

### Fix

**Do not install `npm@latest`** — npm 12 requires Node `^22.22.2`, while Ubuntu apt only ships **22.22.1**. One patch version short and engines rejects it:

```
npm ERR! notsup Required: {"node":"^22.22.2 || ^24.15.0 || >=26.0.0"}
npm ERR! notsup Actual:   {"npm":"9.2.0"}
```

Install **npm 11** instead:

```bash
sudo npm install -g npm@11
hash -r                  # clear the shell's command cache
which npm                # expect /usr/local/bin/npm (not /usr/bin/npm)
npm --version            # 11.x
```

Why this is safe: npm's global prefix is `/usr/local`, so the new version lands in `/usr/local/lib/node_modules/npm` and **does not overwrite** the apt-managed `/usr/share/nodejs/`. Future `apt upgrade` won't conflict.

### Verify

```bash
agentseek task frontend
# added 227 packages, and audited 228 packages, found 0 vulnerabilities
```

---

## Appendix: harmless "errors" in the startup log

None of these are real problems:

| Output | Cause |
|---|---|
| `'SHOW FULL TABLES FROM test' contains unsupported syntax` | sqlglot doesn't parse seekdb's MySQL dialect; falls back to a plain command |
| `[sample_graphs] skipped xxx: No module named 'graphs'` | six built-in demo graphs are absent (this project's graph lives in `src/research_deepagent/`) |
| `npm warn Unknown builtin config "globalignorefile"` | stale option in Ubuntu's `/etc/npmrc` |
| `agent server 0.2.3 needs upgrade to 0.11.0` (Studio banner) | LangGraph Studio's version gate; the two packages use different version schemes; only affects Studio tracing |
| Studio opens automatically, `GET /deploy 404` | Studio probing a deploy endpoint; expected |
