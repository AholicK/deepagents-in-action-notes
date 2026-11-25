# ch02 · Quickstart: Your First Deep Agent and the Model–Tool Loop

> Course: <https://datawhalechina.github.io/deepagents-in-action/chapters/ch02-quickstart/>
> Verified against: deepagents 0.7.8 / langchain 1.4.3 / langchain-openai 1.6.7 / langsmith 0.14.4 / Python 3.13.18
> Tags: **[doc]** = stated in the course · **[verified]** = measured or read from source locally

## TL;DR

`create_deep_agent()` takes **18 parameters** but only three you must understand (`model` / `tools` / `system_prompt`); the other 15 are entry points for chapters 3–16. Your tool functions are not shown to the model as code — they are **compiled into a JSON Schema**, which *is* what the model reads. That translation is the single most useful thing to verify by hand in this chapter.

---

## 1. Environment I actually got

**[doc]** asks for `pip install "deepagents>=0.7,<0.8" langchain-openai`, Python 3.11+.

**[verified]**

| Package | Version |
|---|---|
| deepagents | **0.7.8** |
| langchain | **1.4.3** |
| langgraph | 1.2.14 |
| langchain-core | 1.6.7 |
| langchain-openai | 1.6.7 |
| langsmith | 0.14.4 |
| Python | 3.13.18 |

Two notes:

1. The course says "LangChain 1.0"; what installs today is **1.4.3**. Same major line, minor already at 4. If a traceback disagrees with the tutorial, check this number first.
2. **`deepagents` pulls in `langgraph` itself** — don't install it separately. `pip show deepagents` lists it under `Requires`.

## 2. Hello World: 15 lines, four ideas

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

**① `ChatOpenAI(base_url=...)`** — this is not "OpenAI's model", it's **a client that speaks the OpenAI protocol**. Change `base_url` and the backend becomes SiliconFlow, DeepSeek, Zhipu, Alibaba. That single parameter is how most of the Chinese ecosystem plugs in.

**② `def get_weather(city: str) -> str`** — an ordinary Python function. **No decorator, no base class, no registration.** Deep Agents infers everything from the signature plus the docstring.

**③ `agent.invoke({...})`** — input is a dict whose `messages` is a list. **Output is also a dict**; `result["messages"]` is the **full conversation history**, not just the final answer. `[-1].content` is the human-readable ending.

**④ That `[-1]`** — Python's "last element". The list may hold a dozen entries (user, model requesting tools, tool results, model again…); `[-1]` grabs the closing one.

> **Why does one `invoke()` trigger a dozen model calls?**
> Because `invoke()` means "run this graph to completion", not "call the model once". The graph contains a `model → tools → model` loop, and the model decides how many turns to take.

## 3. It accepts 18 parameters; you need three

**[doc]**'s table lists only `model` / `tools` / `system_prompt`. Here is the real signature.

**[verified]** `inspect.signature(create_deep_agent)`:

| # | Parameter | Default | One-line purpose | Chapter |
|---|---|---|---|---|
| 1 | `model` | `None` → `claude-sonnet-4-6` (**deprecated**) | Model instance or `provider:model` string | this one |
| 2 | `tools` | `None` | Your tool functions | this one |
| 3 | `system_prompt` | `None` | Persona / behavioural bounds | this one |
| 4 | `middleware` | `()` | Extra middleware, inserted after base, before tail | ch04 |
| 5 | `subagents` | `None` | Inline sub-agent definitions | ch05 |
| 6 | `skills` | `None` | Skill directories loaded on demand | ch07 |
| 7 | `memory` | `None` | Memory files loaded at start | ch08 |
| 8 | `permissions` | `None` | Filesystem path rules | ch11 |
| 9 | `backend` | `None` → `StateBackend()` | Where files actually live | ch03 / ch10 |
| 10 | `interrupt_on` | `None` | Pause for approval before given tools | ch09 |
| 11 | `response_format` | `None` | Structured output (Pydantic / TypedDict) | ch14 |
| 12 | `state_schema` | `None` | Extend graph state | advanced |
| 13 | `context_schema` | `None` | Runtime context schema | advanced |
| 14 | `checkpointer` | `None` | Thread-level persistence (resume) | ch08 |
| 15 | `store` | `None` | Cross-thread storage | ch08 |
| 16 | `debug` | `False` | Graph execution logging | debugging |
| 17 | `name` | `None` | Graph name shown in LangSmith | debugging |
| 18 | `cache` | `None` | Node-level cache | advanced |

**On `model=None`:** the course says the default is `claude-sonnet-4-6` but the implicit model is deprecated — **[verified] exactly right**. Source:

```python
if model is None:
    model = get_default_model()      # → ChatAnthropic(model_name="claude-sonnet-4-6")
```

and `get_default_model()` carries `@deprecated(since="0.5.3", removal="1.0.0")`. **Works in 0.7, gone in 1.0.** Always pass a model.

## 4. What you get for free: 8 tools and your own sentence

This is the part I most wanted to measure, because default capability sets the cost of your first line of code.

**[verified]** I intercepted a real call with a "spy model" (subclass `BaseChatModel`, copy the request in `bind_tools` / `_generate`, send nothing over the network):

```python
# Tools bound to the model (default config, system_prompt="test")
['ls', 'read_file', 'write_file', 'edit_file', 'delete', 'glob', 'grep', 'task']

# Messages actually sent
[0] system  len=4     ← just "test"
[1] human   len=2     ← "hi"
```

**① Default tool set = 8: seven file tools + `task`**

| Tool | Purpose |
|---|---|
| `ls` | list directory |
| `read_file` | read a file (with `offset` / `limit`) |
| `write_file` | write a whole file |
| `edit_file` | replace a fragment |
| `delete` | delete a file |
| `glob` | find by filename pattern (`**/*.py`) |
| `grep` | search by content |
| `task` | **delegate a subtask to a sub-agent** |

There is **no `execute`**. `FilesystemMiddleware` defines 8 file tools including `execute`, but `execute` requires a backend that can actually run commands, which the default `StateBackend` cannot provide — so it is not bound. **This is the concrete answer to "why can't my agent run code".**

**② Default system prompt is exactly your sentence, not one character more**

The course says "v0.7 default base prompt is empty" — **[verified] to the character**: I passed `"test"`, the model received `test`.

The design intent: **v0.7 does not write your persona for you.** Earlier harness versions injected a long generic "you are a professional agent…" preamble. v0.7 hands that decision back to the application — cheaper and more controllable, but *you* must write the role clearly or the agent has no idea what it's for.

## 5. The three elements aren't style advice — they're compiler input

**[doc]** calls them: parameter type annotations + docstring + default values. Sounds like a lint rule. It isn't. **All three are translated verbatim into JSON Schema, and that schema is the entire interface the model sees.**

**[verified]** Feeding the course's two functions to `convert_to_openai_tool()`:

```python
def calculate(expression: str) -> float:
    """Evaluate a math expression and return the result.

    Args:
        expression: A math expression, e.g. "1 + 2 * 3".
    """
```

becomes

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

and

```python
def internet_search(query: str, max_results: int = 5,
                    topic: Literal["general","news","finance"] = "general",
                    include_raw_content: bool = False) -> dict:
    """Run a web search for the given query."""
```

becomes

```json
{
  "function": {
    "name": "internet_search",
    "description": "Run a web search for the given query.",
    "parameters": {
      "properties": {
        "query":               {"type": "string"},
        "max_results":         {"default": 5,         "type": "integer"},
        "topic":               {"default": "general", "enum": ["general","news","finance"], "type": "string"},
        "include_raw_content": {"default": false,     "type": "boolean"}
      },
      "required": ["query"],
      "type": "object"
    }
  }
}
```

**The mapping is the whole point:**

| You write | It becomes | Effect on the model |
|---|---|---|
| First docstring line | `description` | *When* to call this tool |
| `Args:` section | per-parameter `description` | *What* to put in each argument |
| Type annotation | `type` | Prevents wrong-typed arguments |
| Default value | `default` + removed from `required` | Model may omit optional args |
| `Literal["a","b"]` | `enum` | **Hard constraint** — the model can only pick from the list |

The last row surprised me: **`Literal` is not just a type hint, it's a lock on the model's output space.** `topic: str` invites `"tech"`; `Literal["general","news","finance"]` makes it impossible.

> Rephrased: **a tool isn't "code shown to the model", it's "a spec sheet shown to the model".** The model never sees the function body — only that JSON. A vague docstring is an illegible spec sheet.

## 6. v0.7's opt-in design: measured before and after

**[doc]** says task planning is no longer default and `TodoListMiddleware` must be passed explicitly. Easy to skim past — so I measured the delta.

**[verified]**

| | Without `TodoListMiddleware` | With it |
|---|---|---|
| Tools bound to model | 8 | **9** (adds `write_todos`) |
| System message | 1 block, **4 chars** | 2 blocks, **1376 chars** |
| The extra 1372 chars | — | The `## write_todos` usage instructions |

The injected block starts:

```
## `write_todos`
You have access to the `write_todos` tool to help you manage and plan complex objectives.
Use this tool for complex objectives to ensure that you are tracking each necessary step.
It is critical that you mark todos as completed as soon as you are...
```

**This is hard evidence that middleware rewrites context**: one middleware does two things at once — appends a tool to `tools`, appends 1372 characters to `system`. Both inside `wrap_model_call`; your business code is untouched.

**So "opt-in" saves more than one tool — it saves 1372 characters of fixed overhead on every request.** A one-shot Q&A doesn't need it; a five-step research job does.

## 7. The model–tool loop: one `invoke()`, many turns

**[doc]**'s diagram is accurate. I cross-checked it against my own trace from the previous round (pre02 deep research):

```
total        313.49 s
LLM calls     46        275.8 s combined (88%)
tool calls    61
```

**61 tool calls = at least 61 loop iterations.** My code contained exactly one `agent.invoke()`.

The skeleton is those 4 nodes:

```
        ┌──────────────────────────────┐
        │                              │
   __start__ → model ──has tool_calls──→ tools ──┘
                 │
                 └──no tool_calls──→ done, return final answer
```

**The only exit condition: does this turn's assistant message contain `tool_calls`?**

- Yes → run `tools`, append results to `messages`, back to `model`
- No → loop ends; that message is the answer

Three beginner confusions this resolves:

| Symptom | Cause |
|---|---|
| One question, 10 messages in `result["messages"]` | Every tool call produces 2 messages (request + result) |
| Slow run, but my tool functions are instant | The 46 model calls dominate, not the tools |
| Model never calls the tool and makes things up | Tool `description` unclear, or system prompt never mentions it |

## 8. LangSmith: how to prove you actually opened the trace

**[doc]** gives four variables:

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your-langsmith-key
LANGSMITH_PROJECT=deepagents-course
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

Three gotchas I hit:

**① Endpoint must match your org's region.** US is the default (`api.smith.langchain.com`); EU uses `eu.api.smith.langchain.com`, APAC uses `apac.api.smith.langchain.com`. **The failure mode is not an error — it's "code runs fine, trace never appears"**, because it was written to a different region.

**② `.env` is not auto-loaded.** `python script.py` won't read it. Use `set -a; source .env; set +a` or `load_dotenv()`.

**③ Environment variables are a process-level snapshot.** Edit `.env`, reopen the terminal (or restart the kernel); running processes keep the old values.

**Counting loop iterations in the trace:** don't count total runs (middleware wrappers and sub-agents inflate it). Filter by `run_type = llm` and `run_type = tool`:

```
LLM 46 / Tool 61
→ 46 "model decisions", 61 "tool executions"
→ several turns requested multiple tools at once (parallel tool_calls)
```

Or via CLI:

```bash
langsmith run list --trace-ids <TRACE_ID> --project deepagents-course \
  --run-type tool --include-metadata --limit 200 --format json > tool.json
```

## 9. Two things I deliberately did not do

1. **Did not run the full Hello World** (`get_weather`). The goal this round was mechanism + hard evidence, so the spy model extracted "what the model actually receives" **at zero cost and zero network calls**. The real API round belongs to the hands-on step.
2. **Did not wire Tavily.** I already ran three full research jobs in pre01/pre02; this chapter reuses that trace data.

## 10. Self-test

1. How many tools does `create_deep_agent()` give you by default, and why is `execute` absent?
2. Does the default system prompt contain anything written by Deep Agents? What design stance does that reflect?
3. What does `Literal["general","news","finance"]` become in JSON Schema, and what error does it prevent?
4. How much does adding `TodoListMiddleware` change the model's context? (Quote the numbers.)
5. When does the model–tool loop stop? What's the condition?
6. Why can `result["messages"]` hold a dozen entries?
7. Code runs, but no trace appears in LangSmith. What do you check first?

---

## Appendix: measurement scripts (no API keys involved)

```python
# 1) real signature
import inspect
from deepagents import create_deep_agent
print(inspect.signature(create_deep_agent))

# 2) how a tool is translated
import json
from langchain_core.utils.function_calling import convert_to_openai_tool
print(json.dumps(convert_to_openai_tool(my_tool), ensure_ascii=False, indent=2))

# 3) intercept the request (no network)
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
