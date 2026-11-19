# ch01 · Agent 三层架构与 Deep Agents 的定位

> 课程原文：<https://datawhalechina.github.io/deepagents-in-action/chapters/ch01-agent-harness/>
> 核实环境：deepagents 0.7.8 / langchain 1.4.3 / langgraph 1.2.14 / Python 3.13.18
> 标注规则：**【原文】**= 课程里写的；**【核实】**= 我在本地装好的 0.7.8 上读源码或跑出来的

## 一句话结论

三层不是三个竞品，是**三层楼**：LangGraph 管「怎么跑起来不崩」，LangChain 管「怎么写得标准」，Deep Agents 管「别再从零造文件工具和子 Agent」。而 Deep Agents 最后交给你的东西，就是一张 LangGraph 编译好的图——我用一行代码验证了这件事。

---

## 1. 先把三层翻译成人话

**【原文】** 的比方是：Runtime 给工作台和电源，Framework 给锤子锯子，Harness 直接给一个装好工具的工具间。

我觉得这个比方少了一句，补上：

| 层 | 它到底是个什么物件 | 类比 |
|---|---|---|
| **Runtime（LangGraph）** | 一台**执行引擎**：把「先跑 A、再跑 B、出错重试、断点续跑」这些事编译成图，然后一步步 tick 下去 | 汽车底盘 + 发动机。你踩油门它才动，但它不懂你要去哪 |
| **Framework（LangChain）** | 一套**标准件**：模型统一接口（换模型不用改代码）、工具统一接口（Python 函数就是一个工具）、Agent 循环本身 | 方向盘、变速箱、仪表盘。装到底盘上就能开了 |
| **Harness（Deep Agents）** | 一个**预装好的套件**：文件读写、子 Agent、上下文压缩、记忆，这些「认真点的 Agent 都要」的东西已经装好挂在墙上 | 整车出厂。你只需要说「去哪」 |

关键点是：**三者是叠上去的，不是三选一**。你可以只用底盘（LangGraph 手搓），也可以装标准件自己开（LangChain `create_agent`），也可以直接开整车（`create_deep_agent`）。

## 2. 我用一行代码证明了「Harness 最终落在 LangGraph 上」

这是本章我最想验证的一句话。**原文说**：`create_deep_agent()` 内部调用 `create_agent()`，最终由 LangGraph 执行。

那就看它返回什么：

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

**【核实】输出**：

```
CompiledStateGraph
['__start__', 'model', 'tools', 'PatchToolCallsMiddleware.before_agent']
```

三件事一次说清：

1. `CompiledStateGraph` 是 **LangGraph 的类**，不是 Deep Agents 自己的类。Harness 没有另造一个运行时，它就是把图配好然后编译。
2. 图里只有 **4 个节点**：开始 → 调模型 → 调工具 → 补工具调用参数。**这就是「模型—工具循环」的全部骨架**，剩下的都是中间件挂在这几个节点上。
3. 名字里带 `PatchToolCallsMiddleware` 说明中间件**直接编译进了图里**，不是外挂的包装器。

> 补充一句给初学的自己：`nodes` 是 LangGraph 的「图上的站点」。`__start__` 是虚拟起点，`model` 是调大模型那一站，`tools` 是执行工具那一站，循环就在 `model → tools → model` 之间转。

## 3. 中间件不是「插件」，是洋葱

**【原文】** 说 Middleware 提供工具、扩展状态、在模型调用和工具执行等环节介入。这话对，但太抽象。我实际拦了一次调用栈，看到的是**一层套一层的洋葱**：

```
model_node（LangChain 的模型节点）
 └─ FilesystemMiddleware.wrap_model_call
     └─ SubAgentMiddleware.wrap_model_call
         └─ SummarizationMiddleware.wrap_model_call
             └─ AnthropicPromptCachingMiddleware.wrap_model_call
                 └─ _execute_model_sync   ← 真正发请求
```

读法：请求从外往里穿，每层都能**改一次请求**（加工具、塞提示词、截断历史、打缓存标记），穿到底才真的发给模型；响应再原路穿回来。

这解释了一件我一开始想不通的事：**为什么「加一个中间件」就能让模型多一个工具？** 因为它在 `wrap_model_call` 里往请求的 `tools` 列表里塞了一个，模型根本不知道这个工具是「内置」还是「你写的」——对它来说都只是一段 JSON Schema。

**【核实】** 默认装配顺序（读 `deepagents/graph.py` 的 docstring，与源码一致）：

| 位置 | 中间件 | 触发条件 |
|---|---|---|
| Base 1 | `SkillsMiddleware` | 传了 `skills=` |
| Base 2 | `FilesystemMiddleware` | **总是有**（必需，不可排除） |
| Base 3 | `SubAgentMiddleware` | 有 inline subagents |
| Base 4 | `SummarizationMiddleware` | 总是有 |
| Base 5 | `PatchToolCallsMiddleware` | 总是有 |
| Base 6 | `AsyncSubAgentMiddleware` | 有异步 subagents |
| — | **你传的 `middleware=[...]` 插在这里** | — |
| Tail | `AnthropicPromptCaching` / `BedrockPromptCaching` / `FireworksPromptCaching` | 有对应包就装，模型不是这家就空转 |

**记住一条**：`FilesystemMiddleware` 和 `SubAgentMiddleware` 是**必需件**，源码里明确写了 `_apply_excluded_middleware` 遇到它们会直接抛 `ValueError`，不允许 profile 把它们摘掉。原因写在注释里：文件工具和 `task` 是「核心特性依赖的脚手架」。

## 4. 为什么非要有 Harness 这一层

**【原文】** 的观察是：成功的 Agent 产品长得都差不多——Claude Code、Manus、Cursor 都是「文件系统 + 任务规划 + 子 Agent + 上下文管理」。

我补一个更实用的判断标准：

> **如果你发现自己在写第 3 个 Agent，而且又双叒在写 read_file / write_file，那你就该用 Harness 了。**

反过来说，如果只写一个 demo、只要一个工具、只要一次问答，那 Harness 反而是负担——它会给你 8 个你根本不会用的工具，占掉上下文。这也是为什么 v0.7 把「任务规划」改成了按需启用（见下一节）。

## 5. Context Engineering：把「塞 prompt」换成「给个文件柜」

这是本章真正的内核，也是我读完最有收获的一段。

**传统做法**（prompt stuffing）：把 20 个文件、5 万字全塞进 system prompt。三个死法：

- **装不下**：上下文窗口有上限
- **看不清**：信息越多，模型对关键信息的注意力越稀
- **不可扩**：项目再大一点就彻底没辙

**Deep Agents 的做法**：给 Agent 一个**虚拟文件系统**。要看哪个文件就 `read_file` 一下，要记东西就 `write_file` 进去，大文件用 `offset`/`limit` 只读需要的段。

**【核实】** 默认后端是 `StateBackend`：

```python
# deepagents/graph.py
backend = backend if backend is not None else StateBackend()
```

`StateBackend` 是什么？**它不是真的磁盘**，文件内容存在 LangGraph 的 state 里（就是那次对话的状态对象）。所以：

- 好处：不用建目录、不用管权限、跑完就没了，开发调试最省事
- 限制：**它不能执行命令**。我实测默认绑定给模型的工具里没有 `execute`，就是这个原因——`execute` 需要「能真跑代码」的后端（本地 Shell 或沙箱），`StateBackend` 给不了

**【原文】** 说后端可以换：内存 / 本地磁盘 / 数据库 / 远程沙箱 / 混合路由。这句话的实际含义是：**同一个 Agent 代码，换一行 `backend=` 就能从「玩具」变成「能干活的」**。这是后面第 3 章和第 10 章的主题。

## 6. 竞品对比：我关心的是哪三行

**【原文】** 给了 Deep Agents / Claude Agent SDK / Codex SDK 的对比表。对现在阶段的我，只有三行有意义：

| 维度 | 为什么现在就该在意 |
|---|---|
| **模型无关** | 我现在用 DeepSeek/硅基，明年可能换别家。绑死一家的 SDK，换模型等于重写 |
| **虚拟文件系统可插拔** | 同一套代码，开发用内存、上线用沙箱，不用改业务逻辑 |
| **Python + TS 双语言** | 我的主战场是 Python，但这行 TS 更多，留了后路 |

其余那些（Hooks、OS 级沙箱、MCP Server 模式）现在看是噪音，等真需要了再回来查。

## 7. 三层怎么选：一个粗暴但好用的判断

**【原文】** 给了三行表格。我把它变成三个问句，从上往下问，第一个「是」就停：

1. **流程是固定的吗？**（比如「先校验 → 再研究 → 再人工审」）→ 是就用 **LangGraph**，把确定性步骤写成节点，只在需要判断的地方塞一个 Agent
2. **只需要「模型 + 工具」的循环，但我想自己控上下文和中间件？** → 是就用 **LangChain `create_agent`**
3. **以上都不是，我要一个能自己读文件、自己拆任务、自己派活的 Agent？** → 用 **Deep Agents `create_deep_agent`**

**原文** 有一句我觉得该划重点：**「如果还没有必须自定义的流程，可以先从 Deep Agents 开始；当需求超出当前抽象提供的控制范围时，再深入 LangChain 或 LangGraph。」**

这句话反过来也成立，而且更重要：**别一上来就用 LangGraph 手搓**。我见过太多教程让人从 `StateGraph` 开始搭 Agent，搭完 200 行代码，功能还不如 `create_deep_agent` 三行。

## 8. 自测题（我自己出的，答不出来就回去重读）

1. `create_deep_agent()` 返回的对象是什么类型？它属于哪一层？
2. 中间件的「洋葱模型」是什么意思？请求是从外往里穿还是从里往外穿？
3. 为什么默认给模型的工具里**没有** `execute`？
4. 默认后端 `StateBackend` 的文件存在哪里？它有什么做不到的事？
5. 三层里哪两层是「必需」的？为什么源码不允许把它们摘掉？
6. 什么情况下**不该**用 Harness？

---

## 附：本章涉及的真实文件位置（方便复查）

```
.venv/lib/python3.13/site-packages/deepagents/graph.py                  # create_deep_agent 全实现
.venv/lib/python3.13/site-packages/deepagents/middleware/filesystem.py  # 8 个文件工具
.venv/lib/python3.13/site-packages/deepagents/middleware/subagents.py   # task 工具
.venv/lib/python3.13/site-packages/langchain/agents/factory.py          # create_agent 与 model_node
```
