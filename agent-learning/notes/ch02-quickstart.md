# ch02 · 快速上手：第一个 Deep Agent 与模型—工具循环

> 课程原文：<https://datawhalechina.github.io/deepagents-in-action/chapters/ch02-quickstart/>
> 核实环境：deepagents 0.7.8 / langchain 1.4.3 / langchain-openai 1.6.7 / langsmith 0.14.4 / Python 3.13.18
> 标注规则：**【原文】**= 课程里写的；**【核实】**= 我在本地跑出来或读源码看到的

## 一句话结论

`create_deep_agent()` 只有三个参数是「必须懂」的（`model` / `tools` / `system_prompt`），但它一共收 **18 个参数**；另外 15 个是后面 13 章的入口。你写的那几个工具函数，最后会被翻译成一段 **JSON Schema** 交给模型——**工具不是「给模型看代码」，是「给模型看说明书」**。这一章最值得亲手验证的就是这个翻译过程。

---

## 1. 环境：我实际的版本

**【原文】** 要求 `pip install "deepagents>=0.7,<0.8" langchain-openai`，Python 3.11+。

**【核实】** 我这边装出来的是：

| 包 | 版本 |
|---|---|
| deepagents | **0.7.8** |
| langchain | **1.4.3** |
| langgraph | 1.2.14 |
| langchain-core | 1.6.7 |
| langchain-openai | 1.6.7 |
| langsmith | 0.14.4 |
| Python | 3.13.18 |

两点提醒：

1. 课程说「LangChain 1.0」，实际装到的是 **1.4.3**。大版本对（都是 1.x），小版本已经跑到 4 了。`create_agent` 的 API 形态没变，但如果你搜到的报错和教程对不上，先看这个数字。
2. **`deepagents` 会自己把 `langgraph` 拖进来**，不用单独装。想确认哪层在干活，看 `pip show deepagents` 的 `Requires` 就行。

## 2. Hello World：代码只有 15 行，但有 4 个知识点

```python
import os
from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent

model = ChatOpenAI(
    model=os.environ.get("MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct"),
    api_key=os.environ["SILICONFLOW_API_KEY"],
    base_url="https://api.siliconflow.cn/v1",
)

def get_weather(city: str) -> str:
    """Get weather for a given city."""
    return f"It's always sunny in {city}!"

agent = create_deep_agent(
    model=model,
    tools=[get_weather],
    system_prompt="You are a helpful assistant.",
)

result = agent.invoke(
    {"messages": [{"role": "user", "content": "北京今天天气怎么样？"}]}
)
print(result["messages"][-1].content)
```

逐块拆：

**① `ChatOpenAI(base_url=...)`** —— 这不是「OpenAI 的模型」，这是「**说 OpenAI 那套话的客户端**」。`base_url` 一改，背后可以是硅基流动、DeepSeek、智谱、阿里云。整个国内生态就靠这一个参数接进来的。

**② `def get_weather(city: str) -> str`** —— 这就是一个普通 Python 函数。**没有装饰器、没有继承、没有注册**。Deep Agents 靠「函数签名 + docstring」自己看懂它。

**③ `agent.invoke({...})`** —— 输入是一个 dict，里面 `messages` 是消息列表。**输出也是 dict**，`result["messages"]` 是**完整对话历史**（不是只有最后一句）。最后一条 `.content` 才是给人看的答案。

**④ 那个 `[-1]`** —— Python 的「取最后一个元素」。`messages` 里可能有十几条（用户问、模型要调工具、工具结果、模型再回答……），`[-1]` 拿的是收尾那条。

> **为什么 `invoke()` 只调一次，背后却可能调十几次模型？**
> 因为 `invoke()` 是「把这张图跑完」，不是「调一次模型」。图里有 `model → tools → model` 的循环，转几次由模型自己决定。**这是本章第二个柱子，后面第 5 节展开。**

## 3. 它一共收 18 个参数，你只需要懂 3 个

**【原文】** 的表格只列了 `model` / `tools` / `system_prompt`。我把真实签名打出来看了一遍：

**【核实】** `inspect.signature(create_deep_agent)`：

| # | 参数 | 默认值 | 一句话作用 | 在哪一章 |
|---|---|---|---|---|
| 1 | `model` | `None` → `claude-sonnet-4-6`（**已废弃**） | 模型实例或 `provider:model` 字符串 | 本章 |
| 2 | `tools` | `None` | 你自己的工具函数列表 | 本章 |
| 3 | `system_prompt` | `None` | 人设 / 行为边界 | 本章 |
| 4 | `middleware` | `()` | 插在 base 之后、tail 之前的中间件 | 第 4 章 |
| 5 | `subagents` | `None` | 内联子 Agent 定义 | 第 5 章 |
| 6 | `skills` | `None` | 技能目录（按需 `read_file` 加载） | 第 7 章 |
| 7 | `memory` | `None` | 启动时加载哪些记忆文件 | 第 8 章 |
| 8 | `permissions` | `None` | 文件路径权限规则 | 第 11 章 |
| 9 | `backend` | `None` → `StateBackend()` | 文件到底存哪 | 第 3/10 章 |
| 10 | `interrupt_on` | `None` | 哪些工具调用前暂停等审批 | 第 9 章 |
| 11 | `response_format` | `None` | 结构化输出（Pydantic / TypedDict） | 第 14 章 |
| 12 | `state_schema` | `None` | 扩展 state 字段 | 进阶 |
| 13 | `context_schema` | `None` | 运行时上下文 schema | 进阶 |
| 14 | `checkpointer` | `None` | 线程级持久化（断点续跑） | 第 8 章 |
| 15 | `store` | `None` | 跨线程存储 | 第 8 章 |
| 16 | `debug` | `False` | 打开图执行日志 | 调试 |
| 17 | `name` | `None` | 图的名字（LangSmith 里显示） | 调试 |
| 18 | `cache` | `None` | 节点级缓存 | 进阶 |

**关于 `model=None` 这件事**：课程表格写「默认 `claude-sonnet-4-6`，但依赖隐式模型已弃用，建议显式指定」——**【核实】完全准确**。源码里：

```python
if model is None:
    model = get_default_model()      # → ChatAnthropic(model_name="claude-sonnet-4-6")
```

而 `get_default_model()` 上挂着 `@deprecated(since="0.5.3", removal="1.0.0")`。**意思是：0.7 还能用，1.0 就彻底没有了**。所以别偷懒不传 model。

## 4. 默认给了你什么：8 个工具 + 一句你的话

这是我最想实测的一段，因为「默认能力」决定了你写第一行代码时的成本。

**【核实】** 用一个「间谍模型」（继承 `BaseChatModel`，在 `bind_tools` 和 `_generate` 里把东西抄下来，不发任何网络请求）拦了一次真实调用：

```python
# 绑定给模型的工具（默认配置，只传 system_prompt="test"）
['ls', 'read_file', 'write_file', 'edit_file', 'delete', 'glob', 'grep', 'task']

# 实际发给模型的消息
[0] system  len=4     ← 只有 "test"
[1] human   len=2     ← "hi"
```

两个结论，都很有价值：

**① 默认工具是 8 个：7 个文件工具 + 1 个 `task`**

| 工具 | 干什么 |
|---|---|
| `ls` | 列目录 |
| `read_file` | 读文件（支持 `offset`/`limit` 分段读） |
| `write_file` | 写整个文件 |
| `edit_file` | 改文件（按片段替换） |
| `delete` | 删文件 |
| `glob` | 按文件名模式找（`**/*.py`） |
| `grep` | 按内容搜 |
| `task` | **把子任务派给子 Agent** |

注意**没有 `execute`**。`FilesystemMiddleware` 里其实有 8 个文件工具（含 `execute`），但 `execute` 需要「能真跑命令」的后端，默认的 `StateBackend` 给不了，所以不绑定。**这条差异会直接影响你判断「为什么我的 Agent 不会跑代码」。**

**② 默认 system prompt 就是你自己写的那句，一个字都没多加**

课程说「v0.7 默认基础提示词为空」——**【核实】准确到字符级**：我传 `"test"`，模型收到的 system 就是 4 个字符的 `test`。

这件事的意义在于：**v0.7 不替你写人设**。以前版本的 Harness 会塞一大段「你是一个专业的 Agent，你应该……」的通用提示词，v0.7 把这个决定权还给了应用。好处是省 token、可控；代价是**你得自己写清楚**，否则 Agent 会不知道自己该干什么。

## 5. 三要素不是「风格建议」，是「编译器输入」

**【原文】** 说工具定义有三要素：参数类型标注 + docstring + 默认值。听起来像代码规范。**不是。这三样东西会被逐字翻译成 JSON Schema，直接决定模型能不能用对工具。**

**【核实】** 我把课程里的 `calculate` 和 `internet_search` 两个函数丢给 `convert_to_openai_tool()`，看它到底翻译成了什么：

```python
def calculate(expression: str) -> float:
    """Evaluate a math expression and return the result.

    Args:
        expression: A math expression, e.g. "1 + 2 * 3".
    """
```

↓ 翻译成 ↓

```json
{
  "type": "function",
  "function": {
    "name": "calculate",
    "description": "Evaluate a math expression and return the result.",
    "parameters": {
      "properties": {
        "expression": {
          "description": "A math expression, e.g. \"1 + 2 * 3\".",
          "type": "string"
        }
      },
      "required": ["expression"],
      "type": "object"
    }
  }
}
```

再看带默认值和 `Literal` 的那个：

```python
def internet_search(query: str, max_results: int = 5,
                    topic: Literal["general","news","finance"] = "general",
                    include_raw_content: bool = False) -> dict:
    """Run a web search for the given query."""
```

↓ 翻译成 ↓

```json
{
  "function": {
    "name": "internet_search",
    "description": "Run a web search for the given query.",
    "parameters": {
      "properties": {
        "query":               {"type": "string"},
        "max_results":         {"default": 5,       "type": "integer"},
        "topic":               {"default": "general", "enum": ["general","news","finance"], "type": "string"},
        "include_raw_content": {"default": false,   "type": "boolean"}
      },
      "required": ["query"],
      "type": "object"
    }
  }
}
```

**这张对照表就是三要素的全部价值**：

| 你写的 | 变成了 | 模型看到的效果 |
|---|---|---|
| docstring **第一行** | `description` | 决定「什么时候该调这个工具」 |
| docstring 的 `Args:` 段 | 每个参数的 `description` | 决定「这个参数该填什么」 |
| 类型标注 `str` / `int` / `bool` | `type` | 模型不会传错类型 |
| 默认值 `= 5` | `default` + **从 `required` 里消失** | 模型可以只填必填项 |
| `Literal["a","b"]` | `enum` | **模型只能在这几个值里选**，不会瞎编 |

最后一条（`enum`）是我之前不知道的：**`Literal` 不只是「类型提示」，它是给模型上的一道锁**。`topic` 如果写成 `str`，模型可能传 `"tech"`；写成 `Literal["general","news","finance"]`，它就只能在这三个里挑。

> 换个说法：**工具不是「给模型看你的代码」，是「给模型看一张说明书」**。模型永远看不到函数体，它只看到这段 JSON。所以 docstring 写得含糊，等于说明书印糊了。

## 6. v0.7 的「按需启用」：我对比了开关前后

**【原文】** 说 v0.7 不再默认启用任务规划，需要 `write_todos` 时要显式传 `TodoListMiddleware`。这话很容易读过去，我实测了一下差异：

**【核实】**

| | 不加 `TodoListMiddleware` | 加了 |
|---|---|---|
| 绑定给模型的工具 | 8 个 | **9 个**（多 `write_todos`） |
| system message | 1 个 block，**4 字符** | 2 个 block，**1376 字符** |
| 多出来的 1372 字符是什么 | — | `## write_todos` 的使用说明 |

多出来的那段开头是：

```
## `write_todos`
You have access to the `write_todos` tool to help you manage and plan complex objectives.
Use this tool for complex objectives to ensure that you are tracking each necessary step.
This tool is very helpful for planning complex objectives, and for breaking down these larger
complex objectives into smaller steps.
It is critical that you mark todos as completed as soon as you are...
```

**这就是「中间件能改上下文」的硬证据**：一个中间件同时干了两件事——往 `tools` 里加一个工具，往 `system` 里加 1372 字符的说明书。这两件事都发生在 `wrap_model_call` 里，你的业务代码一行没改。

**所以「按需启用」省下的不只是 1 个工具，是每次请求 1372 个字符的固定开销。** 短任务（问一句答一句）完全不需要它；长任务（要拆 5 步以上）才值得付这个钱。

## 7. 模型—工具循环：`invoke()` 一次，背后转了几圈

这是本章第二个柱子。**【原文】** 的图画得很清楚，我用自己的 trace 数据对了一遍。

**【原文】** 说研究任务可能调 10+ 次工具。我上一轮跑的真实 trace（pre02 那次深度研究）：

```
总耗时      313.49 s
LLM 调用     46 次      合计 275.8 s（占 88%）
工具调用     61 次
```

**61 次工具调用 = 循环至少转了 61 圈。** 而我代码里只有一次 `agent.invoke()`。

循环的骨架就是图里那 4 个节点：

```
        ┌──────────────────────────────┐
        │                              │
   __start__ → model ──有 tool_calls──→ tools ──┘
                 │
                 └──没有 tool_calls──→ 结束，返回最终回答
```

**判定条件只有一个：模型这轮返回的消息里有没有 `tool_calls`。**

- 有 → 去 `tools` 节点执行，结果写回 `messages`，再回 `model`
- 没有 → 循环结束，这条消息就是最终回答

这解释了几个新手常见的困惑：

| 现象 | 原因 |
|---|---|
| 明明只问了一句话，`result["messages"]` 有 10 条 | 每次工具调用产生 2 条（模型请求 + 工具结果） |
| 跑得很慢，但我的工具函数很快 | 慢在 46 次模型调用，不是工具 |
| 模型一直不调工具，直接瞎编 | 工具的 `description` 没写清，或 system prompt 没提这个工具 |

## 8. LangSmith：怎么确认「我真的点开看过了」

**【原文】** 给了四个环境变量：

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your-langsmith-key
LANGSMITH_PROJECT=deepagents-course
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

三个我踩过的点：

**① Endpoint 必须和你的组织区域一致。** 默认是 US（`api.smith.langchain.com`）。EU 组织要用 `eu.api.smith.langchain.com`，APAC 用 `apac.api.smith.langchain.com`。**用错区域的表现不是报错，是「代码跑通了但 Trace 里什么都没有」**——因为写到了另一个区域。

**② `.env` 不会自动加载。** 直接 `python script.py` 不读 `.env`。要么 `set -a; source .env; set +a`，要么在代码里 `load_dotenv()`。

**③ 环境变量是「进程级快照」。** 改了 `.env` 必须重开终端/重启内核，正在跑的进程读不到新值。

**在 Trace 里怎么数「来回了几次」**：不要数总 Run 数（里面有 middleware 包装、有子 Agent）。**直接筛 `run_type = llm` 和 `run_type = tool`，两个数字一减就知道**：

```
LLM 46 次 / Tool 61 次
→ 46 次「模型决策」，61 次「工具执行」
→ 说明有好几轮模型一次要了多个工具（并行 tool_calls）
```

命令行也行（上一轮就是这么数的）：

```bash
langsmith run list --trace-ids <TRACE_ID> --project deepagents-course \
  --run-type tool --include-metadata --limit 200 --format json > tool.json
```

## 9. 我这次没做的两件事（留个账）

1. **没跑完整的 Hello World**（`get_weather` 那个）。我这次的目标是「把机制搞懂 + 拿到硬证据」，所以用「间谍模型」在**不花一分钱、不发一次网络请求**的前提下，把「模型到底收到了什么」扒了出来。真跑一次 API 留给实操环节。
2. **没接 Tavily**。研究助手那节我上一轮（pre01/pre02）已经跑过 3 次完整研究，这次跳过，直接复用 trace 数据。

## 10. 自测题

1. `create_deep_agent()` 默认给你几个工具？为什么没有 `execute`？
2. 默认 system prompt 里有 Deep Agents 自己加的话吗？这说明 v0.7 的什么设计取向？
3. `Literal["general","news","finance"]` 在 JSON Schema 里变成了什么？它防住了什么错误？
4. 加了 `TodoListMiddleware` 之后，模型收到的上下文变了多少？（要能说出数字）
5. 模型—工具循环什么时候停？判定条件是什么？
6. `agent.invoke()` 返回的 `messages` 为什么可能有十几条？
7. LangSmith 的 Trace 没出现，但代码跑通了，先查什么？

---

## 附：本章实测脚本（不含任何 API Key）

```python
# 1) 打印真实签名
import inspect
from deepagents import create_deep_agent
print(inspect.signature(create_deep_agent))

# 2) 看工具被翻译成什么
import json
from langchain_core.utils.function_calling import convert_to_openai_tool
print(json.dumps(convert_to_openai_tool(my_tool), ensure_ascii=False, indent=2))

# 3) 拦截真实请求（不发网络）
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration

CAP = {}
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
