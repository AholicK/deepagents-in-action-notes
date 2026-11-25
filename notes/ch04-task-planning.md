# DeepAgents in Action · ch04 任务规划与分解（单篇笔记）

> 环境：WSL2 Ubuntu 26.04.1 ｜ deepagents **0.7.8** / langchain **1.4.3** / langgraph **1.2.14**
> 模型：`deepseek-v4-pro`（主实验）、`deepseek-v4.1-flash`（对照）
> 搜索：Tavily（每次 3 条结果）
> 数据：本仓库 `experiments/ch04/*.json`，全部为本地真实运行，无手写数字
> 打卡对应：Task4 ① 显式启用规划 ② 小型研究文档 Agent + Trace ③ 问题复盘

---

## 0. 一句话结论

**任务规划不是让模型变聪明，是给它一张自己写、自己勾的清单**：清单存在 Agent State 的 `todos` 字段里，靠 `TodoListMiddleware` 一次性注入「工具 + 状态字段 + 1372 字符说明书」。
但**注入 ≠ 使用**：我实测同一个 Agent，3 步任务它一次都没调用 `write_todos`，5 步任务才规划。规划是模型的决定，不是框架的保证。

---

## 1. 为什么需要规划：我先踩了「不规划」的坑

### 1.1 简单任务 vs 复杂任务

课程的说法很直白：一步能答完的（「北京今天天气」）不需要清单；需要多源检索、对比、成文的（「调研三个竞品写 3000 字报告」）才需要。缺少清单的典型症状是：漏步骤、重复搜同一个词、上下文变长后忘了整体进度。

### 1.2 第一次实测：3 步任务，`write_todos` 一次都没调

我按课程原文写了 system_prompt（「先用 write_todos 制定研究计划…」），任务给的是：

> 调研 LangGraph 1.0 相比 0.x 的三个主要变化，写 400 字摘要，每个变化标来源。搜索最多 3 次。

模型 `deepseek-v4.1-flash` 的结果：

| 指标 | 数值 |
|---|---|
| 耗时 | 13.9 s |
| AI 消息 | 3 条 |
| 工具调用 | 3 次，全是 `internet_search` |
| `write_todos` 调用 | **0 次** |
| `result["todos"]` | `[]` |

它直接搜了 3 次、写了 1398 字符的报告，质量不差——但**清单根本不存在**。

这就是课程里那句话的实证：**「工具存在不代表每个任务都会调用；具体行为仍由模型、提示词和任务复杂度共同决定。」** 我原本以为「加了中间件它就会规划」，实际是「加了中间件它**才能**规划」。

### 1.3 第二次：5 步任务 + 写死规则，它规划了

同一套代码，只改两处：任务拆成 5 个明确子步骤，system_prompt 里把「3 步以上必须先调 write_todos」写成硬规则。模型换成 `deepseek-v4-pro`。

结果：77.3 s，9 次工具调用，`write_todos` 调了 **3 次**，清单 5 项完整走完 4 项（最后一项见 §4.3）。

**结论**：触发规划的不是中间件，是「任务复杂度 + 提示词约束 + 模型能力」三件事同时到位。

> **补一个更硬的证据（后来才挖到）**：`write_todos` 的**工具描述**里明写着——
>
> ```
> If the user's request is trivial and takes less than 3 steps,
> it is better to NOT use this tool and just do the task directly.
> ```
>
> 所以第一次「3 步不规划」不是模型偷懒，是**按说明书执行**。模型的「不规划」和「规划」都是被这份说明书指挥的——这正好呼应 ch02 那句「工具不是给模型看代码，是给模型看说明书」。

---

## 2. 显式启用：开关前后的硬数字

课程说 v0.7 默认不装 `TodoListMiddleware`，要显式传。我没直接信，用**不联网的 Spy 模型**（继承 `BaseChatModel`，在 `bind_tools` 里抄工具清单、在 `_generate` 里抄 system prompt）各跑了一次：

| | 默认 `create_deep_agent(model, tools=[])` | 加 `middleware=[TodoListMiddleware()]` |
|---|---|---|
| 绑定给模型的工具 | **8 个**：ls / read_file / write_file / edit_file / delete / glob / grep / task | **9 个**：多一个 `write_todos` |
| system prompt 字符数 | **0**（不传 system 就是空） | **1372** |
| 状态 schema 字段 | files / messages / structured_response | 多一个 **`todos`** |

### 2.1 一个容易看错的细节：`system_chars` 不是 `len(content)`

第一版探针我直接 `len(system_msg.content)`，得到 **1**——因为 system 的 `content` 不是字符串，是 **content-block 列表**（Anthropic 风格），列表里只有一个 `{"type": "text", ...}` 块。要先拼出 `text` 再算长度，才是 1372。

> 这个坑值得记：**LangChain 里「消息内容」有两种形态**（纯字符串 / 块列表），做字符统计、截断、匹配时都要先归一化。

### 2.2 另一个容易看错的细节：schema 有 `todos` ≠ 运行时一定有值

探针里加了中间件后，输出 JSON Schema 多出 `todos` 字段；但那次运行的返回值 `state.keys()` 仍然只有 `files` 和 `messages`——因为 Spy 模型没调用 `write_todos`，**没有写入就没有这个键**。

所以判断「有没有规划能力」要看 **schema / 工具清单**，判断「这次有没有规划」要看 **实际 state 和工具调用记录**。两件事不能混。

---

## 3. `write_todos` 长什么样

### 3.1 数据结构

每一项就两个字段：

```json
{ "content": "调研 Deep Agents 的虚拟文件系统", "status": "in_progress" }
```

- `content`：这一步要干什么（自然语言，给模型自己看）
- `status`：三种状态之一

### 3.2 三种状态

| 状态 | 含义 | 谁写的 |
|---|---|---|
| `pending` | 待办，还没开始 | 模型规划时写 |
| `in_progress` | 正在做 | 模型开始某步时写 |
| `completed` | 做完了 | 模型做完某步时写 |

**关键**：这是**模型自己写的进度标记**，不是框架强制的状态机。课程原文也提醒了：`completed` 只代表「模型认为做完了」，产物对不对要另外查（见 §6 复盘）。

### 3.3 说明书里的 5 条硬指令（这一节是整章的钥匙）

我一开始以为清单行为是「模型习惯」。后来把两处文字挖出来——注入的 1372 字符 system + `write_todos` 的工具描述——发现**每一条现象都能对上一条指令**。

| 指令原文（出处） | 它导致的现象 |
|---|---|
| 「If the user's request is trivial and takes less than 3 steps, it is better to NOT use this tool」（工具描述） | 3 步任务 **0 次**调用 |
| 「IMPORTANT: When you write this todo list, you should mark your first task (or tasks) as **in_progress immediately**!」（工具描述） | 第一次写清单**不是全 pending**，第 1 项直接 `in_progress` |
| 「Mark tasks complete IMMEDIATELY after finishing (**don't batch completions**)」+「You can make several updates to the todo list at once」（工具描述，两句并存） | 模型**攒一批再改**——两句本身有张力，模型选了后者 |
| 「Unless all tasks are completed, you should **always have at least one task in_progress**」（工具描述） | 最后一项长期停在 `in_progress` |
| 「When you finish all work, write your final answer in the message **AFTER your last `write_todos` call**」（注入 system）+「Marking the last todo complete is **not itself an answer**」（工具描述） | 写完报告就结束，**不再回头补最后一个勾** |
| 「The `write_todos` tool should **never be called multiple times in parallel**」（注入 system） | 状态更新是串行的，不会和别的 `write_todos` 并发 |

**结论：模型不是「自由发挥」，是在执行一份写得很细的说明书。** 这也解释了为什么「清单全绿」不能当验收标准——说明书只要求它「标记」，没要求它「验证」。

> 顺带说一个矛盾点：工具描述一边说「完成即标，别攒」，一边说「可以一次改多项」。模型实际选择了「攒一批再改」（5 次搜索后一次标 3 项完成）。**说明书自相矛盾时，模型会挑对自己省事的那条。**

### 3.4 工具的真实 JSON Schema（实测）

`status` 不是自由字符串，是 `enum`（硬锁），模型写不出第四种状态：

```json
{
  "properties": {
    "todos": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "content": {"type": "string"},
          "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]}
        },
        "required": ["content", "status"]
      }
    }
  },
  "required": ["todos"]
}
```

这和 ch02 讲的 `Literal` → `enum` 是同一件事：**约束放在 schema 层，比写在 prompt 里可靠**。

---

## 4. 任务①：规划过程（真实时间线）

### 4.1 实验设置

- 模型：`deepseek-v4-pro`
- 中间件：`[TodoListMiddleware()]`
- 任务：5 步报告（调研 Deep Agents 虚拟文件系统 / Claude Code 的 CLAUDE.md / OpenAI Agents SDK 的 Session → 写 `/notes.md` → 800 字对比报告）
- 观测方式：`agent.stream(stream_mode="values")`，每步读 `state["todos"]`，变化才记快照

### 4.2 时间线

| 时刻 | 发生了什么 | 清单状态（5 项） |
|---|---|---|
| t=11.6 s | 第 1 次 `write_todos` | 第 1 项 `in_progress`，其余 4 项 `pending` |
| t=15.3 s | 并行发 3 个搜索（三个框架各一） | 不变 |
| t=24.2 s | 再发 2 个补充搜索 | 不变 |
| t=33.2 s | 第 2 次 `write_todos` | 前 3 项 `completed`，第 4 项 `in_progress` |
| t=56.2 s | `write_file` 写 `/notes.md` | 不变 |
| t=60.7 s | 第 3 次 `write_todos` | 前 4 项 `completed`，第 5 项 `in_progress` |
| t=77.3 s | 直接输出报告，结束 | 第 5 项**仍是 `in_progress`** |

工具序列：

```
write_todos → internet_search ×5 → write_todos → write_file → write_todos → (报告)
```

### 4.3 三条结论

1. **它确实「先列清单再干活」**：第一次 `write_todos` 在 11.6 s，早于任何搜索。
2. **但不是「全 pending 再开始」**：第一次就把第 1 项标成 `in_progress`。课程示意图画的是「全部 pending → 逐项推进」——但工具描述里明确要求「write this todo list 时立刻把第一项标 `in_progress`」，所以**这是照做，不是跑偏**。
3. **打勾是批量的，最后一项不闭合**：5 次搜索攒完才更新一次状态（工具描述允许「一次改多项」），最后一步「写报告」停在 `in_progress`（两条指令叠加：「未全部完成时至少保留一个 `in_progress`」+「最终答案写在最后一次 `write_todos` 之后」）。

> 如果只看「清单是否全部 completed」来判断任务完成，这次会误判成「没做完」——但报告其实写完了。反过来，如果只看报告，又会以为清单全绿。**清单和产物必须一起看**，这就是任务③要复盘的东西。

---

## 5. 任务②：官方示例（三大 Harness 对比）+ LangSmith Trace

### 5.1 设置

- 任务与 system_prompt **都用课程原文**（不加我自己那条「3 步以上必须规划」的硬规则），这样能看到「官方示例本身能不能触发规划」
- 模型：`deepseek-v4-pro`；搜索每次 3 条
- Trace：`LANGSMITH_TRACING=true`，项目 `deepagents-course`

### 5.2 结果

| 指标 | 数值 |
|---|---|
| 耗时 | **101.1 s** |
| AI 消息 | 8 条 |
| 工具调用 | **17 次**：12 次搜索 + 4 次 `write_todos` + 1 次 `write_file` |
| 最终报告 | **2,401 字符**（含对比表格 + 选型建议 + 小结） |
| 最终 `todos` | **5 / 5 全部 `completed`** |

### 5.3 清单流转（本地记录，与 trace 对过）

| 时刻 | 动作 | 清单状态 |
|---|---|---|
| t=8.0 s | 第 1 次 `write_todos` **+ 同时并行 3 个搜索** | 第 1 项 `in_progress`，4 项 `pending` |
| t=16.1 s | 并行 3 个搜索 | 不变 |
| t=26.9 s | 并行 3 个搜索 | 不变 |
| t=47.6 s | 并行 2 个搜索 | 不变 |
| t=55.3 s | 第 2 次 `write_todos` | 前 3 项 `completed`，第 4 项 `in_progress` |
| t=55.3 s | 再补 1 个搜索 | 不变 |
| t=81.8 s | 第 3 次 `write_todos` | 前 4 项 `completed`，第 5 项 `in_progress` |
| t=81.8 s | `write_file` → `/workspace/agent_harness_comparison.md` | 不变 |
| t=87.0 s | **第 4 次 `write_todos`** | **5 项全部 `completed`** |
| t=87.0 s+ | 输出最终报告 | 结束 |

### 5.4 和任务①的关键差别：这次闭合了

同样是 `deepseek-v4-pro`、同样类型的多步任务：

| | 任务①（我加强制规则） | 任务②（课程原文提示词） |
|---|---|---|
| 清单项数 | 5 | 5 |
| `write_todos` 次数 | 3 | **4** |
| 最后一项 | 停在 `in_progress` | **标了 `completed`** |
| 报告 | 1,694 字符 | 2,401 字符 |

**结论：清单闭不闭合不稳定，同一模型同类任务也会变。** 所以「清单全绿」不能当验收标准，得看产物（下一节）。

### 5.5 Trace 里看到了什么

| trace 指标 | 数值 |
|---|---|
| root 状态 | `success` |
| LLM run | 7 个，合计 **83.1 s**（占总耗时 101.1 s 的 **82%**） |
| 最慢单次 LLM | 25.0 s |
| tool run | 16 个 |
| trace 链接 | `https://smith.langchain.com/o/f414948a-…/projects/p/deepagents-course/r/01a21180-…?trace=01a21180-…` |

**82% 的时间在模型生成**，和 Task1-3 那次 313 s trace 的结论（88%）一致——**这类 Agent 的瓶颈永远是 LLM，不是搜索工具**。

> 一个诚实的坑：本地记录 17 次工具调用，trace 里只数到 16 个 `tool` run。原因是 `list_runs(limit=100)` 的**上限就是 100 条**，这条 trace 的 chain run 有 77 个，加上 llm/tool 刚好顶到 100，再分页查询又超时。**「本地记录」和「trace 统计」是两套账，数量对不上时先查口径（limit / 是否含包装层），别急着下结论。**

---

## 6. 任务③：问题复盘——清单 vs 实际产物

### 6.1 三样东西逐项查

**① `result.get("todos", [])` 的最终状态**

```json
[
  {"content": "调研 Deep Agents 框架的核心能力与定位", "status": "completed"},
  {"content": "调研 Claude Agent SDK 的核心能力与定位", "status": "completed"},
  {"content": "调研 Codex SDK 的核心能力与定位", "status": "completed"},
  {"content": "对比三大框架核心能力差异并整理要点", "status": "completed"},
  {"content": "撰写并输出简要分析报告", "status": "completed"}
]
```

5 项全 `completed`，`todo_stats = {pending: 0, in_progress: 0, completed: 5}`。

**② Trace 里实际调了哪些工具**

- `write_todos` ×4（t=8.0 / 55.3 / 81.8 / 87.0）
- `internet_search` ×12（分 5 批：3 + 3 + 3 + 2 + 1）
- `write_file` ×1（`/workspace/agent_harness_comparison.md`）

**③ 最终报告是否覆盖清单**

| 检查项 | 结果 |
|---|---|
| 三个框架都出现 | ✅ Deep Agents / Claude Agent SDK / Codex SDK 全命中 |
| 有对比表格 | ✅ 至少 3 张表（总体定位 / 选型建议 / 差异小结） |
| 有选型建议 | ✅ 「需求 → 推荐」表 |
| 有结论 | ✅ 一句话总结 |
| 报告字数 | 2,401 字符 |

### 6.2 复盘发现的三个问题

**问题 1：清单项和报告标题不是字面对应**

我先用「清单前 8 个字符是否出现在报告里」做机器匹配，结果 5 项全是 `false`。但人工看报告，五个方面全写到了——报告用的是「一、总体定位」「二、核心能力差异」这种结构，不是照抄清单文字。

**教训**：机器检查「清单 vs 产物」时，**要用实体/关键词匹配，不能用原文前缀匹配**。否则会误判成「没覆盖」。

**问题 2：清单全绿 ≠ 产物正确，清单没绿 ≠ 没做完**

- 任务①：最后一项停在 `in_progress`，但报告写完了 → 只看清单会误判「没做完」
- 任务②：5 项全绿，但报告质量要另查（引用是否真实、对比是否准确）→ 只看清单会误判「做对了」

课程原文那句「`completed` 是 Agent 写入的进度标记，应用仍需检查产物」不是客套话，是这一章最容易踩的坑。

**问题 3：模型说「已保存」，要确认保存到哪了**

报告最后一句是「（完整报告已保存至 `/workspace/agent_harness_comparison.md`）」。`write_file` 确实调了，路径也对——但**默认 `StateBackend` 的 `/workspace` 是虚拟路径，文件存在 Agent State 的 `files` 字段里，不在磁盘上**（ch03 已验证：同 thread 换 agent 能读到，新 thread 报 `File not found`）。

**教训**：看到「已保存」先问「存到哪个后端」。要落磁盘得换 `FilesystemBackend`，要跨进程得配 Store/数据库。

### 6.3 这次复盘的净结论

1. **规划确实发生了**：两次运行都是「先 `write_todos`，再搜索」，不是先干后补。
2. **清单是「粗粒度」的**：5 项覆盖了任务主干，但没细化到「每个框架搜几次」；模型实际搜了 12 次，清单只有 3 个调研项。
3. **状态更新是「批处理」**：不是每步一勾，是攒一批改一次（内置提示词要求 `write_todos` 串行、不并行）。
4. **闭合与否不稳定**：同模型同任务类型，一次闭合一次不闭合。
5. **验收要看三样**：`todos` 状态 + 工具调用记录 + 产物本身，缺一样都可能误判。

---

## 7. 机制：`TodoListMiddleware` 到底注入了什么

加一个中间件，Agent 同时获得三样东西：

| 注入物 | 具体是什么 | 我的证据 |
|---|---|---|
| **1 个工具** | `write_todos`，参数是 `todos: [{content, status}]` | Spy 模型 `bind_tools` 截到 9 个工具 |
| **1 个状态字段** | `todos`，独立于 `messages` 保存 | 输出 JSON Schema 多出 `todos` |
| **1372 字符提示词** | 什么时候该用、三种状态怎么流转、不要并行调用、最终答案写在哪 | Spy 模型 `_generate` 截到 system |

### 7.1 为什么清单不会被「上下文压缩」吃掉

`todos` 和 `messages` 是**两个独立字段**。第 3 章的对话总结（`SummarizationMiddleware`）压缩的是 `messages`，不会删除 `todos`——所以长任务跑到第 6 步时，即使前面的搜索结果被压缩成摘要，清单还在，Agent 仍知道「总共几步、哪步没做」。

课程原文的说法是「锚定作用」，我的理解：**清单是压缩后唯一还完整的「任务地图」**。

### 7.2 跨次运行要接续，得靠 Checkpointer

只加 `TodoListMiddleware` 不会让第二次 `invoke()` 接上第一次的清单。要接续需要：

```python
agent = create_deep_agent(
    model=model,
    middleware=[TodoListMiddleware()],
    checkpointer=InMemorySaver(),   # 进程内
)
# 两次 invoke 用同一个 thread_id
config = {"configurable": {"thread_id": "task4-demo"}}
```

`InMemorySaver` 只活在当前进程；进程重启后还要恢复，得换数据库型 Checkpointer（第 8 章）。

**实测验证**（`04_verify_claims.py`，用 Scripted 模型，零 token）：

| 场景 | `todos` | `messages` 条数 |
|---|---|---|
| 第 1 次 `invoke`（thread=`task4-verify`） | 2 项（1 completed + 1 in_progress） | 4 |
| 第 2 次 `invoke`（**同一个** thread） | **2 项还在** | 6（累积） |
| 第 3 次 `invoke`（**换一个** thread） | **`<missing>`** | 2（全新） |

**同一 `thread_id` 才能接上；换 thread 就是一张白纸。** 这和第 3 章验证的 Backend 行为是同一套逻辑：状态存在 checkpointer 里，按 `thread_id` 分区。

### 7.3 子 Agent 默认不继承清单

默认的 `general-purpose` 子 Agent 和 `subagents=[...]` 声明的子 Agent，**都不会继承主 Agent 的 `TodoListMiddleware`**。要给子 Agent 规划能力，得在它自己的 `middleware` 里加。隔离模式下子 Agent 的清单存在自己的 `todos` 里，不读主清单、也不写回。

---

## 8. 中间件全景：三种配置方式（这是本章的「地图」）

`create_deep_agent()` 的本质就是「把一组中间件自动组装到 Agent 上」。配置方式分三类：

| 配置方式 | 中间件 | 作用 |
|---|---|---|
| **默认就有** | `FilesystemMiddleware` | 7 个文件工具 + 权限规则 |
| | `SummarizationMiddleware` | 上下文自动压缩（阈值可配） |
| | `PatchToolCallsMiddleware` | 补齐历史里缺失的工具响应 |
| **专用参数** | `subagents=` → `SubAgentMiddleware` | `task` 工具 + 子 Agent 委派 |
| | `skills=` → `SkillsMiddleware` | 注入技能包 |
| | `memory=` → `MemoryMiddleware` | 注入 AGENTS.md |
| | `interrupt_on=` → `HumanInTheLoopMiddleware` | 人工审批拦截 |
| **`middleware=[...]`** | `TodoListMiddleware` | 任务规划（本章主角） |
| | `PIIMiddleware` / `ToolRetryMiddleware` / `ModelFallbackMiddleware` / `ToolCallLimitMiddleware` / `ContextEditingMiddleware` | 脱敏、重试、降级、限流、清理 |

**同名实例是「原位置换」，不是「叠加合并」**：传入同名的 `SummarizationMiddleware` 会替换默认那个，且不会把新旧字段合并——替换后要自己验证阈值、Backend 等配置是否还成立。

### 8.1 三个容易混淆的职责（课程专门列了表）

| 遇到的问题 | 谁负责 | 注意 |
|---|---|---|
| 历史里有工具调用、没有响应 | `PatchToolCallsMiddleware` 补一条说明消息 | 不重试、不验证结果 |
| 工具调用抛可重试异常 | `ToolRetryMiddleware`（要显式配） | 写操作要考虑重复执行 |
| 下一次运行接上次状态 | **Checkpointer** + 同一个 `thread_id` | 不是 middleware 参数 |
| 工具返回了，但内容对不对 | 应用自己的校验/评测/人工 | 清单完成 ≠ 结果正确 |

---

## 9. 自测题（我自己出的，答不出来就回去重读）

1. v0.7 里不加 `TodoListMiddleware`，`create_deep_agent()` 默认给模型几个工具？有 `write_todos` 吗？
2. 加了这个中间件，除了多一个工具，还多了哪两样东西？（要能说出 1372 这个数字）
3. 输出 JSON Schema 里有 `todos`，但某次运行 `state.keys()` 里没有 `todos`，怎么解释？
4. 三种状态分别是什么？谁负责写？框架会强制状态流转吗？
5. 为什么我这次实测「最后一项永远停在 `in_progress`」？和哪条内置提示词有关？
6. 清单存在哪个字段？对话总结（`SummarizationMiddleware`）会不会把它删掉？
7. 想让第二次 `invoke()` 接上第一次的清单，需要配什么？只加中间件够吗？
8. 子 Agent 会继承主 Agent 的清单吗？要让它规划该怎么办？
9. `write_todos` 的工具描述里，哪一句解释了「3 步任务不规划」？哪一句解释了「第一次就把第一项标 `in_progress`」？哪一句解释了「最后一项停在 `in_progress`」？

---

## 附：复现方式

```bash
# 环境：WSL2，复用 research_deepagent 的 venv（deepagents 0.7.8）
cd experiments/ch04
PY=/home/aholick/projects/research_deepagent/.venv/bin/python

# ① 开关对比（零成本，不发网络请求）
$PY 01_probe_middleware.py

# ② 多步任务 + 清单时间线
MODEL=deepseek-v4-pro $PY 02_run_planning.py

# ③ 官方示例 + LangSmith Trace + 复盘
MODEL=deepseek-v4-pro $PY 03_run_harness_report.py

# ④ 验证两个硬事实：write_todos 的 schema + Checkpointer 接续
$PY 04_verify_claims.py
```

密钥从 `research_deepagent/.env` 读取（`OPENAI_API_KEY` / `OPENAI_API_BASE` / `TAVILY_API_KEY` / `LANGSMITH_*`），脚本里不落任何 key。
