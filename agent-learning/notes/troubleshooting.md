# 故障排查实录：4 个真实踩过的坑

本文记录 pre01–pre02 过程中遇到的 4 个故障。每个都包含**症状、诊断过程、根因、修法、预防**，全部来自实际复现（不是推测）。

---

## 1. 页面彻底卡死：thread state 膨胀到 23 MB

### 症状

浏览器完全无响应，输入框点不动，甚至切标签都卡。但：

- `curl http://127.0.0.1:2024/ok` → `200`
- 后端进程 CPU 不为 0

### 诊断过程

先排除「后端挂了」：`/ok` 是 200，服务活着。然后查 thread 状态：

```bash
curl -s "http://127.0.0.1:2024/threads/<tid>/state" -o state.json
ls -lh state.json      # 23M ← 问题在这里
```

解析 files 字段：

```python
import json
d = json.load(open("state.json"))
files = d["values"]["files"]
sizes = sorted(((len(str(v)), k) for k, v in files.items()), reverse=True)[:5]
for n, k in sizes:
    print(f"{n:>10,}", k)
```

输出：

```
1,468,190  /large_tool_results/call_01_ET_0LP6V7pRkEVMKuyjFepP8859
1,046,xxx  /large_tool_results/call_01_IGo15rWB3pMGnxPJobgn3369
   ...
   523,564  /conversation_history/session_xxx.md
    13,231  /final_report.md          ← 报告本身很小
```

**30 多个 `/large_tool_results/*`，每个 300 KB–1.4 MB，合计 20+ MB。**

### 根因

模板 `tools.py` 的 `fetch_webpage_content`：

```python
response = httpx.get(url, ...)
response.raise_for_status()
return markdownify(response.text)      # ← 整页转 markdown，无任何长度限制
```

`tavily_search` 对每条结果都这么抓，`max_results=3` → 单次搜索最多返回 3 个完整网页。子 Agent 并行跑 10+ 次 → 30 次搜索 → 20 MB。

DeepAgents 会把超一定大小的工具结果溢写到 `values.files['/large_tool_results/*']`，而**前端加载时会下载整个 thread state** → 浏览器主线程解析 23 MB JSON 直接死。

### 修法（5 行，逻辑不动）

`src/research_deepagent/tools.py`：

```python
# 顶部，tavily_client = TavilyClient() 之后
MAX_PAGE_CHARS = 8000

# fetch_webpage_content 里
def fetch_webpage_content(url: str, timeout: float = 15.0) -> str:
    ...
    response.raise_for_status()
    text = markdownify(response.text)
    if len(text) > MAX_PAGE_CHARS:
        omitted = len(text) - MAX_PAGE_CHARS
        text = text[:MAX_PAGE_CHARS] + f"\n\n[... truncated {omitted} chars ...]"
    return text
```

**必须改在 `fetch_webpage_content` 内部**——主 Agent 和子 Agent 都从这里拿正文，改一处全覆盖。

改完验证：

```bash
.venv/bin/python -c "import ast; ast.parse(open('src/research_deepagent/tools.py').read())"
.venv/bin/python -c "import sys; sys.path.insert(0,'src'); from research_deepagent.tools import MAX_PAGE_CHARS; print(MAX_PAGE_CHARS)"
```

`agentseek-api` 用 `StatReload`，会自动重载（终端出现 `Detected file changes, reloading`）。

### 效果

| | 改之前 | 改之后 |
|---|---|---|
| 单次搜索 | 3 个完整网页（最大 1.4 MB） | 3 × 8000 = 24 KB |
| 30 次累计 | ~20 MB | ~720 KB |
| 新 thread state | 23 MB | **160 KB** |
| 前端 | 卡死 | 正常 |

### 预防

- 开新会话时用**裸根路径** `http://127.0.0.1:5174`，带旧 `?thread=` 参数会再卡一次
- 旧的大 state 已落进 seekdb，**救不回来**

---

## 2. run 状态卡在 `running`：一直转圈

### 症状

页面没有冻死，但一直显示 **"Research in progress"**，输入框禁用。等多久都不变。

### 诊断过程

```bash
TID=<thread-id>

# 1) state 里数据齐了吗
curl -s "http://127.0.0.1:2024/threads/$TID/state" | python3 -c "
import sys, json
d = json.load(sys.stdin)
v = d.get('values', {})
print('messages:', len(v.get('messages', [])))
print('todos:', [(t['status'], t['content'][:20]) for t in (v.get('todos') or [])])
print('next:', d.get('next'))
"
```

输出：

```
messages: 35
todos: [('completed', ...) × 4]
next: []                            ← 图已经结束
```

```bash
# 2) run 状态呢
curl -s "http://127.0.0.1:2024/threads/$TID/runs" | python3 -c "
import sys, json
for r in json.load(sys.stdin):
    print(r['status'], r['run_id'][:20], r.get('created_at'), r.get('updated_at'))
"
```

输出：

```
running  08d13b78-0e1c-4db7-a   2026-11-16T02:06:32.821   2026-11-16T02:06:32.862
                                  ↑ 创建后 40 毫秒就再没更新过
```

**矛盾点：`next: []`（图跑完了）+ run `status: running`（没收尾）。**

### 根因

`agentseek-api` **0.2.3** 的缺陷：SSE 客户端连接断开后，后台图继续跑完，但 run 状态不会被更新为 `success`。前端 `useStream` 看到 `status=running` 就一直 `isLoading=true`，永远等一个不会来的结束信号。

**触发条件**：研究跑到一半时刷新页面、关标签，或浏览器把标签冻结（见坑 #3）。

### 修法

```bash
curl -X POST "http://127.0.0.1:2024/threads/<tid>/runs/<rid>/cancel"
```

状态变 `error` 后刷新页面，**已生成的全部内容都能看到**（数据不丢）。

导出产物：

```bash
curl -s "http://127.0.0.1:2024/threads/<tid>/state" -o st.json
python3 -c "
import json
rep = json.load(open('st.json'))['values']['files']['/final_report.md']['content']
open('report.md','w',encoding='utf-8').write(rep)
print('saved', len(rep), 'chars')
"
```

### 别急着重启服务

先 cancel。重启会丢掉内存里的会话，而且不解决根因。

**唯一该重启的情况**：`ps` 看到 `runtime_entrypoint` 的 `%CPU` 长期 40%+ 而所有 run 已终态——那是运行时在空转（挂过大 state 会话后出现）。

重启前确认端口清空：

```bash
ss -lntp | grep -E ':2024|:5174' || echo "端口已清空"
```

---

## 3. 放到后台标签也会卡：Chrome 冻结后台标签

### 症状

研究跑到一半切到别的标签看别的，回来发现又转圈了——**明明没刷新页面**。

### 根因

三层叠加：

1. 前端 `useStream` 靠一条 **SSE 长连接**接收事件
2. **Chrome 会节流后台标签**：定时器降到 1 次/分钟；长时间无交互的标签直接进入 frozen 状态，网络连接被挂起
3. SSE 一断，后端图照跑（它不依赖连接），但 `agentseek-api` 不更新 run 状态 → 卡 `running`（就是坑 #2）

### 结论（硬结论）

**这个模板跑深度研究时，页面必须保持在前台可见标签。**

「切到别的标签」不等于「保持页面打开」。

### 缓解方案

| 方案 | 效果 |
|---|---|
| 跑的时候别切走 | 最可靠 |
| `chrome://flags/#disable-background-timer-throttling` + `#disable-backgrounding-occluded-windows` 设为 Enabled | 能缓解，不保证 |
| 卡了就 cancel + 刷新 | 兜底 |

---

## 4. `npm ERR! Cannot read properties of null (reading 'edgesOut')`

### 症状

`agentseek task frontend` 直接失败：

```
npm ERR! Cannot read properties of null (reading 'edgesOut')
npm ERR! A complete log of this run can be found in:
npm ERR!     /home/<user>/.npm/_logs/2026-11-16T00_56_40_430Z-debug-0.log
```

### 诊断过程

看日志的关键行：

```bash
tail -35 ~/.npm/_logs/<log>.log | grep -E "at |npm "
```

输出：

```
at [loadPeerSet] (/usr/share/nodejs/@npmcli/arborist/lib/arborist/build-ideal-tree.js:1304)
at async Install.exec (/usr/share/nodejs/npm/lib/commands/install.js:146)
npm v9.2.0
timing ... idealTree:node_modules/vitest
```

关键信息：

- `/usr/share/nodejs/` → 这是 **Ubuntu/debian 的打包路径**，apt 把 npm 拆成几十个独立 deb
- `loadPeerSet` 崩在 **vitest** 的 peer 依赖解析
- npm 版本 **9.2.0**（2023 年初）

### 根因

npm 9.2.0 的 arborist 在处理某些嵌套 peer 依赖时会读到 null。这是已知 bug，npm 10+ 已修。

### 修法

**不要装 `npm@latest`**——npm 12 要求 Node `^22.22.2`，而 Ubuntu apt 只到 **22.22.1**，差一个 patch 就会被 engines 拒绝：

```
npm ERR! notsup Required: {"node":"^22.22.2 || ^24.15.0 || >=26.0.0"}
npm ERR! notsup Actual:   {"npm":"9.2.0"}
```

正确做法是装 **npm 11**：

```bash
sudo npm install -g npm@11
hash -r                  # 清 shell 命令缓存
which npm                # 应该是 /usr/local/bin/npm（不是 /usr/bin/npm）
npm --version            # 11.x
```

为什么安全：npm 的 global prefix 是 `/usr/local`，新版装到 `/usr/local/lib/node_modules/npm`，**不覆盖** apt 管理的 `/usr/share/nodejs/`，以后 `apt upgrade` 不会冲突。

### 验证

```bash
agentseek task frontend
# added 227 packages, and audited 228 packages, found 0 vulnerabilities
```

---

## 附：其他无害的「假错误」

启动日志里这些都**不是错误**，不要浪费时间：

| 输出 | 原因 |
|---|---|
| `'SHOW FULL TABLES FROM test' contains unsupported syntax` | sqlglot 不认 seekdb 的 MySQL 方言，回退成普通命令执行 |
| `[sample_graphs] skipped xxx: No module named 'graphs'` | agentseek-api 内置的 6 个 demo 图找不到（本项目的图在 `src/research_deepagent/`） |
| `npm warn Unknown builtin config "globalignorefile"` | Ubuntu 自带 `/etc/npmrc` 里的旧配置项 |
| `agent server 0.2.3 needs upgrade to 0.11.0`（Studio 顶部黄条） | LangGraph Studio 的版本号要求，两个包的版本体系不同，只影响 Studio tracing |
| Studio 自动打开、`GET /deploy 404` | Studio 在探测部署接口，正常 |
