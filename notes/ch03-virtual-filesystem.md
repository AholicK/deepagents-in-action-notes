# DeepAgents in Action · ch03 学习笔记（单篇合订）

> 覆盖 **Lec 04 虚拟文件系统与上下文管理** + **Lec 05 可插拔存储后端**。
> 全部结论在 `deepagents 0.7.8` 上实测，代码在 [`experiments/ch03/`](../experiments/ch03/)，原始结果在 `experiments/ch03/results/*.json`。
> 环境：WSL2 Ubuntu 26.04.1 / Python 3.13.18 / deepagents 0.7.8 / langgraph 1.2.14 / langchain-core 1.6.7。

---

## 0. 这一章在讲什么（30 秒版）

前两章说「Agent = 模型 + 工具 + 循环」，模型每一轮只能看见 prompt 里的东西。
这一章解决的是：**资料太多，prompt 装不下，怎么办。**

答案不是「压缩 prompt」，是**给 Agent 一个文件柜**：

| 人的做法 | Agent 的对应 |
|---|---|
| 资料分门别类放抽屉 | `write_file` 写进虚拟文件系统 |
| 需要时抽出来看 | `read_file` 按 offset/limit 读 |
| 按标签找文件 | `glob` 按模式匹配 |
| 全文检索找那句话 | `grep` 搜字面量 |
| 便签记中间结果 | 同上，只是路径不同 |
| 抽屉放哪由你决定 | **Backend**：state / 磁盘 / Store |

### 一句话结论

> **文件系统不是「存储功能」，是上下文管理机制。**
> 它把「模型必须现在看到」和「模型需要时再看」拆开了 —— 这一步拆开，才谈得上长任务。

### 6 条实测硬结论

| # | 结论 | 证据 |
|---|---|---|
| 1 | 默认绑 **8 个工具**：7 个文件工具 + `task`，**没有 `execute`** | `bind_tools` 截获的入参 |
| 2 | 卸载阈值 20,000 tokens = **精确 80,000 字符**（`NUM_CHARS_PER_TOKEN = 4`） | 源码常量 + 实测触发点 |
| 3 | 一次真实卸载：工具返回 **150,165 字符** → 模型实收 **2,389 字符**，压缩 **62.9 倍** | LangSmith trace 的两个 run 对比 |
| 4 | 7 个内置工具**全部**在卸载豁免名单里，但 `read_file` 会用同一个 80,000 字符预算**原地截断** | 对照组实测：读 2000 行只回 994 行 + `next_offset` |
| 5 | `StateBackend` 同 thread 换 agent 实例能读到，新 thread 读不到（`File not found`） | exp3 场景 1 |
| 6 | `FilesystemBackend(virtual_mode=True)` 会拦 `../` 越界：`Error: Path traversal not allowed` | exp1b 场景 5 |

---

## 第一部分 · 为什么用文件系统管上下文

### 1. 先把「上下文」这个词拆开

初学者容易把「上下文」理解成「聊天记录」。实际不是。

**上下文（context）= 这一次请求里，模型能看见的全部 token。** 它由 8 层拼起来（人格 → 项目规则 → 长期记忆 → 技能清单 → 环境事实 → 工具定义 → 会话历史 → 本条消息）。

问题在于：**这 8 层是有预算的**。模型窗口假设 128k tokens，工具定义占 5k，历史占 50k，剩下给资料的就没多少了。

传统做法是「塞」：搜索结果、网页正文、中间计算，全往会话历史里堆。
Deep Agents 的做法是「存」：**先把资料写进文件，会话历史里只留一句「东西在 /path/xxx」**。

### 2. 七个工具，各自的真实返回格式

课程给了「工具 / 用途 / 类比」三列表格。但**真正写代码时你要知道返回长什么样**，否则解析会错。这是我实测的：

| 工具 | 入参（真实签名） | 返回（实测原文） |
|---|---|---|
| `ls` | `path` | `['/notes/task3.md']`（Python list 的 repr）；空目录返回 `No files found` |
| `read_file` | `file_path`, `offset=0`, `limit=100` | ` 1  # Task3 实验笔记\n 2  \n...` —— **行号 + 两个空格**，不是 Tab |
| `write_file` | `file_path`, `content` | `Updated file /notes/task3.md` |
| `edit_file` | `file_path`, `old_string`, `new_string`, `replace_all=False` | `Successfully replaced 1 instance(s) of the string in '/notes/task3.md'` |
| `delete` | `file_path` | `Deleted /notes/task3.md` |
| `glob` | `pattern`, `path=None` | `['/notes/task3.md']`；空结果 `No files found` |
| `grep` | `pattern`, `path=None`, `glob=None`, `output_mode='files_with_matches'`, `max_count=None` | 见下 |

**`grep` 三种模式的实测格式**（同一个 pattern `create_agent`，三个文件）：

```
# output_mode="files_with_matches"
/proj/a.py
/proj/b.py
/proj/c.md

# output_mode="content"
/proj/a.py:
  1: def create_agent():
/proj/b.py:
  1: def create_agent():
/proj/c.md:
  1: create_agent 在文档里也出现了一次

# output_mode="count"
/proj/a.py: 1
/proj/b.py: 1
/proj/c.md: 1
```

要点：
- `content` 模式是 **`<文件路径>:` 单独一行，然后 `  行号: 行内容`**（两个空格缩进）。只给匹配的那一行，**不给上下文行**。
- `glob` 参数是**文件名过滤器**，不是单独的 glob 工具调用。`glob="*.py"` 只搜 .py 文件。
- `pattern` 是**字面量**，不是正则。搜 `a.b` 就只匹配 `a.b` 这三个字符。

### 3. `read_file` 的两个特性

**特性一：分片读取。** 默认 `limit=100`（只读前 100 行）。大文件必须自己算 offset：

```python
read_file("/workspace/report.md")                          # 1-100 行
read_file("/workspace/report.md", offset=100, limit=50)    # 101-150 行
```

注意 `offset` 是 **0-indexed**（从 0 开始数），但返回的行号是 **1-indexed**（从 1 开始标）。这两个不是一回事，第一次用容易懵。

**特性二：原生多模态。** 图片 / 视频 / 音频 / PDF-PPT 都能读成多模态内容块。但有三层前提（课程说了，我确认这是真的）：
1. 文件工具能构造多模态块 ✓
2. Backend 能提供二进制内容
3. **模型供应商接受这种输入模态** ← 这条最容易踩，不是所有模型都收 PDF

---

## 第二部分 · 上下文自动管理

### 4. 大结果卸载：20,000 token 到底是多少字符

课程说「超过约 20,000 tokens 时自动卸载（按字符数估算）」。**「约」和「按字符数估算」是两个含糊词，我去源码里挖了准确值。**

```python
# deepagents/middleware/filesystem.py:905
NUM_CHARS_PER_TOKEN = 4

# filesystem.py:1626
tool_token_limit_before_evict: int | None = 20000
human_message_token_limit_before_evict: int | None = 50000
```

换算：

| 对象 | token 阈值 | 实际字符阈值 | 在哪配 |
|---|---|---|---|
| 工具返回结果 | 20,000 | **80,000 字符** | `FilesystemMiddleware(tool_token_limit_before_evict=...)` |
| 超长用户消息 | 50,000 | **200,000 字符** | `human_message_token_limit_before_evict` |

**这两个数不能混用**。课程提醒过一次，我在源码里确认了它们是两个独立参数。

### 5. 一次真实卸载的全过程

实验：自定义工具 `huge_dump(2000)` 返回 2,000 行 × 74 字符 = **147,999 字符 ≈ 36,999 tokens**，稳稳超过 20k。

**模型收到的变成了这样**（实测原文，1,411 字符）：

```
Tool result too large, the result of this tool call c1 was saved in the
filesystem at this path: /large_tool_results/c1

You can read the result from the filesystem by using the read_file tool,
but make sure to only read part of the result at a time.
...
Here is a preview showing the head and tail of the result:

1  line 00000 | xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
2  line 00001 | xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
3  line 00002 | xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
4  line 00003 | xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
5  line 00004 | xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

... [1990 lines truncated] ...

1996  line 01995 | xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
...
2000  line 01999 | xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

三个细节值得记住：

1. **落盘路径不是课程示意里的 `/workspace/search_results_001.md`**，真实路径是 `/large_tool_results/<tool_call_id>`。我这次 tool_call_id 是 `c1`，路径就是 `/large_tool_results/c1`。
   → 含义：**同一个 tool_call_id 重复卸载会覆盖同一个文件**，不是每次新建编号。
2. 预览是 **前 5 行 + 后 5 行**，中间插 `... [N lines truncated] ...`，每行最多截 1,000 字符（源码 `_create_content_preview(head_lines=5, tail_lines=5)`）。
3. 文件确实进了 state：`result["files"]` 的键就是 `['/large_tool_results/c1']`。

**然后 `read_file` 能读回来** —— 实测返回 `line 00000 ...`，证明「卸载 ≠ 丢失」。

### 6. LangSmith trace 里长什么样（这是 Task1「输入 3M 但 input <9k」的答案）

同一个 trace 里，两个 run 的大小对比：

| run | 类型 | inputs | outputs |
|---|---|---|---|
| `huge_dump` | tool | 15 字符 | **150,165 字符**（原始全文） |
| 第二次 `ScriptedChatModel` | llm | **2,389 字符** | 394 字符 |

**150,165 ÷ 2,389 = 62.9 倍。**

也就是说：
- **trace 里能查到工具真实返回的 150k 全文**（审计、复查、排错用）
- **模型实际只收到 2.4k**（文件引用 + 首尾预览）

这就解释了 Task1 里那个困惑：`输入 3M 但 input <9k`。**不是模型看不见，是中间件在发给模型之前把大块内容换成了「文件路径 + 预览」。**

> trace 链接：`https://smith.langchain.com/projects/p/deepagents-course/r/57a18e0d-aa9a-4283-a0b3-217ea4e1f461`
> run_id：`57a18e0d-aa9a-4283-a0b3-217ea4e1f461`

### 7. 豁免名单 ≠ 无限：`read_file` 的原地截断（课程没讲透的一点）

源码里的豁免名单：

```python
# filesystem.py:1486
TOOLS_EXCLUDED_FROM_EVICTION = (
    "ls", "glob", "grep", "read_file", "edit_file", "write_file", "delete",
)
```

**7 个内置工具全在里面** —— 也就是说它们不会被「卸载成文件引用」。课程说了这一句。

但课程**没说后半句**：它们仍然受同一个 80,000 字符预算约束，只是处理方式从「卸载」变成「**原地截断 + 分页提示**」。

实测（对照组）：写一个 147,999 字符的文件，然后 `read_file(limit=2100)` 整读：

```
返回字符数：79,930        ← 卡在 80,000 以下
是否被卸载：False         ← 没有变成文件引用
是否读到全文：False       ← 只读到第 994 行
返回尾部：
  ... [You can use offset and limit to continue reading ...]
  [Read 994 lines (lines 1-994 of 2000 total). 1006 lines remaining from offset 994.]
```

**结论：豁免 ≠ 一次能读无限多。** 内置工具用「分页」代替「卸载」，两种机制共享同一个 80,000 字符预算，只是对外表现不同：

| | 通用工具（自定义） | 内置文件工具 |
|---|---|---|
| 超预算时 | 写进 `/large_tool_results/`，返回文件引用 | **原地截断**，返回已读行数 + `next_offset` |
| 模型怎么拿全 | `read_file` 按 offset 分段读 | 再调一次 `read_file(offset=994)` |
| 会话历史里剩什么 | 1.4k 的引用 + 预览 | 79.9k 的截断正文 |

这也说明：**`read_file` 的 `limit` 参数不是「读多少给多少」**，还有一层字符预算在下面兜着。

### 8. 对话历史总结（和卸载是两件事）

| | 大结果卸载 | 对话历史总结 |
|---|---|---|
| 触发条件 | 单条工具返回 > 80,000 字符 | 上下文达到模型窗口的 85% |
| 处理对象 | 一条 ToolMessage | 一批旧消息 |
| 做法 | 换成文件引用 + 首尾预览 | 用 LLM 生成结构化摘要（意图/产出物/下一步） |
| 原始数据 | 存在 `files` 里 | 写进 Backend 存档，state 里保留 |
| 谁做 | `FilesystemMiddleware` | `SummarizationMiddleware` |

**两个都要有**：卸载管「单次返回太大」，总结管「聊了太久累积太多」。

---

## 第三部分 · 可插拔后端（这一章最该亲手做的部分）

### 9. 四种后端实测对比

同一段代码（写一个 `/memo.txt`，内容是 `xxx 里的 hello`），只换 backend：

| 后端 | 文件存哪 | 同 thread 新 agent | 新 thread | 进程/实例重启 |
|---|---|---|---|---|
| **StateBackend**（默认） | LangGraph state 的 `files` 键 | ✅ 读到 `state 里的 hello` | ❌ `Error: File '/memo.txt' not found` | 看 checkpointer 策略 |
| **FilesystemBackend** | 真磁盘 `/tmp/ch03_fs_root/memo.txt` | ✅ | ✅ | ✅ 磁盘还在就在 |
| **StoreBackend** | LangGraph `BaseStore` | ✅ | ✅ 读到 `store 里的 hello` | ❌ 换新 `InMemoryStore` 就 `not found` |
| **CompositeBackend** | 按路径前缀分派 | — | `/memories/` ✅ / 其他 ❌ | 同左 |

**磁盘证据**（FilesystemBackend 场景，WSL 里直接看）：

```
$ cat /tmp/ch03_fs_root/memo.txt
磁盘上的 hello
```

文件真的在磁盘上，不是内存里假装有。

### 10. StateBackend：默认，但别误解「临时」

```python
agent = create_deep_agent(model=model)   # 默认就是 StateBackend
```

它的文件活在 **LangGraph 的 state** 里（`files` 键）。实测两条边界：

- **同 thread + 换一个新 agent 实例 → 能读到**。因为文件在 state（checkpointer 里），不在 agent 对象里。这就是为什么「接 checkpointer + 复用 thread_id」能续上。
- **新 thread → 读不到**，报 `Error: File '/memo.txt' not found`。

课程说「并非结束对话就立即删除，取决于 checkpointer 的保存与清理策略」—— 实测确认：**删不删是 checkpointer 的事，不是 agent 的事**。用 `MemorySaver` 时它一直在内存里；用 SQLite checkpointer 就一直在库里。

**什么时候选它**：学习和实验、一次性任务、子 agent 之间传中间产物。零配置。

### 11. FilesystemBackend：落盘，但要小心它能看到什么

```python
agent = create_deep_agent(
    model=model,
    backend=FilesystemBackend(root_dir=".", virtual_mode=True),
)
```

实测三个点：

1. **`root_dir` 是虚拟根**。`/memo.txt` → `<root_dir>/memo.txt`。写进去磁盘上真有。
2. **`virtual_mode=True` 会拦越界**：读 `/../ch03_outside_secret.txt` 返回
   `Error: Path traversal not allowed: /../ch03_outside_secret.txt`，而且**越界写的文件确实没被创建**（我查了 `ls /tmp/ch03_escape.txt` → 不存在）。
3. **但它不是沙箱**。`virtual_mode=True` 只做路径字符串检查，不隔离进程、不限制符号链接。课程那句「这不是进程隔离或安全沙箱」是准确的。

> ⚠️ 真实风险：Agent 能读 `root_dir` 下所有文件，包括 `.env`、私钥。**Web 服务/对外 API 绝对不能用这个后端。**

**什么时候选它**：本地编程助手、CI 流水线、需要人肉看产物的实验。

### 12. StoreBackend：跨线程，但「持久」取决于你塞什么 Store

```python
store = InMemoryStore()          # 开发用
agent = create_deep_agent(
    model=model,
    backend=StoreBackend(namespace=lambda rt: (rt.server_info.user.identity,)),
    store=store,
)
```

实测：

- **跨 thread 能读到** ✅ —— 换一个 thread_id、换一个 agent 实例，`/memo.txt` 照样在。
- **换一个全新的 `InMemoryStore()` 就读不到** ❌ —— 因为 `InMemoryStore` 就是进程内字典，进程一重启全没。

**这一条最容易误判**：课程标题写「跨会话持久化」，但 `InMemoryStore` 只跨 thread、不跨进程。真持久要换 `PostgresStore` / `RedisStore` 之类。

> 本地 invoke 的坑：`rt.server_info` 是 `None`，直接 `rt.server_info.user.identity` 会 `AttributeError`。必须兜底：
> ```python
> namespace=lambda rt: (
>     (rt.server_info.user.identity,) if getattr(rt, "server_info", None) else ("local-user",)
> )
> ```

**什么时候选它**：长期记忆、用户偏好、累积知识库。

### 13. CompositeBackend：路径前缀就是「分区」

```python
backend=CompositeBackend(
    default=StateBackend(),
    routes={"/memories/": StoreBackend(namespace=ns)},
)
```

实测结果：

| 写哪 | 走哪个后端 | 新 thread 还在吗 |
|---|---|---|
| `/workspace/plan.md` | StateBackend | ❌ `File not found` |
| `/memories/pref.txt` | StoreBackend | ✅ `长期偏好` |

**这就是「草稿纸 + 记忆库」共存的实现方式**：不是两个 agent，是**一个 agent 的两个路径前缀**。

课程提了一句「根目录 `ls` 会列出默认后端内容及挂载目录，跨路由的 `glob`/`grep` 会合并结果并恢复路径前缀」—— 这个我没单独测，但逻辑上成立（CompositeBackend 按最长前缀匹配后转给对应后端）。

### 14. 后端选择：我自己的判断表

课程给了一张表，我把它改成「按我会遇到的情况」：

| 我要干什么 | 选谁 | 为什么 |
|---|---|---|
| 跑教程、试 prompt、验证机制 | StateBackend | 零配置，文件跟 state 走 |
| 让 Agent 改我电脑上的真项目 | FilesystemBackend + `virtual_mode=True` | 落盘才能 git diff |
| 想让 Agent 记住「我是谁、偏好什么」 | StoreBackend + 持久 Store | 跨 thread |
| 既要草稿纸又要记忆库 | CompositeBackend | 路径分区 |
| 要跑 `pip install` / 执行用户上传的代码 | **沙箱后端** | 唯一有隔离的 |

**一条判断线：只要「Agent 能执行命令」或「输入来自外部」，就必须上沙箱。** 本地 shell 后端和 FilesystemBackend 都只是「方便」，不是「安全」。

---

## 第四部分 · 权限与自定义后端

### 15. `FilesystemPermission`：三条规则要记

```python
permissions=[
    FilesystemPermission(operations=["write"], paths=["/policies/**"], mode="deny"),
]
```

1. **`mode` 三种**：`allow`（放行）/ `deny`（拒绝）/ `interrupt`（暂停等人批）。
2. **求值顺序是 first-match-wins**：按声明顺序，第一个同时匹配 `operations` 和 `paths` 的规则决定结果；没匹配就默认允许。→ **具体的规则要写在宽泛的规则前面**。
3. **`mode="interrupt"` 需要 checkpointer**，恢复走 `Command(resume=...)`，和工具审批同一套协议。

### 16. v0.7 的删除坑：`write` 权限也管删除

课程这段提醒值得单独记：v0.7 把**递归删除**列为不兼容变更，而且在 `FilesystemPermission` 里，**删除属于 `write` 权限类别**。

后果：你写了 `deny write /workspace/policies/**`，看起来保护住了。但两个请求能绕过去：

- 删 `/workspace/policies`（没有末尾斜杠，不匹配 `/**`）
- 删 `/workspace`（上级目录，递归带走）

课程给的修法是**按目录层级判断**：

```python
target.is_relative_to(directory)                  # 目标在保护目录内 → 拦
or (deleting and directory.is_relative_to(target)) # 删的是保护目录的祖先 → 也拦
```

**这两行是整个 ch03 最容易漏的逻辑。** 只检查前缀字符串（`startswith`）一定会漏。

如果只想关掉内置 delete：`FilesystemMiddleware(tools=[...])` 里不列 `delete`（但要保留 `read_file`）。注意这**不限制自定义工具或 shell 里的删除**。

### 17. 自定义后端要实现的 7 个方法

```python
class S3Backend(BackendProtocol):
    def ls(self, path) -> LsResult: ...
    def read(self, file_path, offset=0, limit=2000) -> ReadResult: ...
    def write(self, file_path, content) -> WriteResult: ...
    def edit(self, file_path, old_string, new_string, replace_all=False) -> EditResult: ...
    def grep(self, pattern, path=None, glob=None) -> GrepResult: ...
    def glob(self, pattern, path="/") -> GlobResult: ...
    def delete(self, file_path) -> DeleteResult: ...   # v0.7 新增
```

两个细节：
- 外部存储后端（S3/Postgres）写成功时 `files_update=None` —— 因为它不在 state 里，不需要回写 `files` 键。
- 包装器（`PolicyWrapper`）**必须同步转发 `delete`**，不能只保护 `write`/`edit`。

### 18. v0.7 的 `backend=` 不能传工厂函数

课程标了，我记一下：

```python
# ✅ 对
backend=CompositeBackend(default=StateBackend(), routes={...})

# ❌ v0.7 已移除
backend=lambda rt: CompositeBackend(...)
```

但 `StoreBackend(namespace=lambda rt: ...)` **仍然可以** —— 它算的是「存到哪个命名空间」，不是「创建哪个后端」。这两个 lambda 不是一回事。

---

## 第五部分 · 我踩到的边界（课程没写或写得含糊的）

### 19. 五个补充实测

| # | 我遇到的 | 实测结果 | 为什么重要 |
|---|---|---|---|
| 1 | `grep` 的 `count` 模式，1500 个匹配显示多少？ | **1000**，附 `Note: the search stopped early ... The matches above are valid but incomplete.` | **`count` 的数字也可能是被 cap 的截断值，不是真实总数。** 别拿它做统计 |
| 2 | 空目录 `ls` / 空 `glob` 返回什么？ | 都是 `No files found` | 课程 v0.7 说了，确认无误；解析时别当空字符串 |
| 3 | `write_file` 同名文件是覆盖还是追加？ | **完整覆盖**（写两次，第二次只有一行，读回只有一行） | v0.7 的破坏性行为；改局部内容必须用 `edit_file` |
| 4 | `read_file` 返回的行号分隔符 | **两个空格**（` 1  content`），不是 Tab | 课程 v0.7 提了；写解析器要注意 |
| 5 | `virtual_mode=True` 能挡 `../` 吗？ | 能，`Error: Path traversal not allowed`，越界文件没创建 | 但**不挡符号链接**，也不是沙箱 |

### 20. 自测题（12 题，答不出来就回去重读）

**基础（1-4）**
1. 7 个内置文件工具分别是什么？默认 `create_deep_agent` 绑几个工具？
2. `read_file` 的 `offset` 从几开始？返回的行号从几开始？
3. `grep` 三种 `output_mode` 各返回什么形状？
4. `write_file` 对同名文件是覆盖还是追加？

**上下文管理（5-8）**
5. 卸载阈值 20,000 tokens 换算成字符是多少？为什么是「按字符估算」？
6. 卸载后模型看到的内容有哪三部分？
7. 为什么 7 个内置文件工具不会被卸载？那它们超长时怎么处理？
8. 「大结果卸载」和「对话历史总结」解决的是同一个问题吗？

**后端（9-12）**
9. StateBackend 的文件在同一个 thread 里换 agent 实例还在吗？换 thread 呢？
10. StoreBackend + `InMemoryStore` 能跨进程持久吗？为什么？
11. CompositeBackend 里 `/memories/` 和 `/workspace/` 各走哪个后端？新 thread 分别还在吗？
12. 什么情况下必须用沙箱后端，FilesystemBackend 为什么不够？

---

## 附：可复现代码清单

```
experiments/ch03/
├── _scripted.py          ScriptedChatModel：按剧本返回 tool_calls，不发网络
├── exp1_tools.py         7 个工具全跑一遍 + files 变化轨迹
├── exp1b_edges.py        5 个 v0.7 边界（空结果/三种 grep/1000 上限/覆盖写/越界）
├── exp2_eviction.py      大结果卸载 + 读回 + 对照组
├── exp2b_trace.py        带 LangSmith tracing 跑一次卸载，输出 run_id
├── exp3_backends.py      四种后端对比（8 个断言）
└── results/              每次运行的 JSON 原始结果
```

跑法（WSL，项目根目录）：

```bash
cd ~/projects/research_deepagent
.venv/bin/python experiments/ch03/exp1_tools.py
.venv/bin/python experiments/ch03/exp1b_edges.py
.venv/bin/python experiments/ch03/exp2_eviction.py
.venv/bin/python experiments/ch03/exp2b_trace.py     # 需要 .env 里的 LANGSMITH_API_KEY
.venv/bin/python experiments/ch03/exp3_backends.py
```

**为什么用 `ScriptedChatModel` 而不是真模型**：
- 真模型可能不按你说的顺序调工具，实验结果不可复现；
- 这个实验要验证的是**中间件 + 后端**的行为，不是模型能力；
- 零 token 消耗，随便重跑。

`ScriptedChatModel` 只有 30 行，核心是 `bind_tools` 返回 self + `_generate` 按索引吐消息。

---

## 一句话收尾

ch01 讲「Agent 是什么」，ch02 讲「怎么跑起来」，ch03 讲「**怎么让它不爆上下文**」。

这三章串起来是一条线：
> 模型只能看见 prompt → prompt 有预算 → 所以要给文件柜 → 文件柜放哪由 Backend 决定 → Backend 决定这东西是「草稿纸」还是「记忆」。

下一章讲任务规划（`write_todos`），那是**在文件系统之上**再加一层「我接下来要做什么」。
