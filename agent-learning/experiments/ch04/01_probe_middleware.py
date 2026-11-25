"""ch04 实验 1：验证「v0.7 默认没有 write_todos，必须显式加 TodoListMiddleware」。

做法：用 Spy 模型（继承 BaseChatModel，不发网络请求），
在 bind_tools 里抄下「框架绑定给模型的工具清单」，
在 _generate 里抄下「真正发给模型的 system prompt」。
对比两组：
  A. create_deep_agent(model=spy, tools=[])
  B. create_deep_agent(model=spy, tools=[], middleware=[TodoListMiddleware()])
输出 JSON，供笔记引用。
"""
import json
import os
import sys

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


def content_text(content) -> str:
    """system 的 content 可能是字符串，也可能是 content-block 列表，统一成纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                parts.append(b.get("text", ""))
            else:
                parts.append(str(b))
        return "\n".join(parts)
    return str(content)



class SpyModel(BaseChatModel):
    """不联网的假模型：只记录框架塞给它的东西。"""

    seen_tools: list = []
    seen_system: str = ""
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "spy"

    def bind_tools(self, tools, **kwargs):
        names = []
        for t in tools:
            if isinstance(t, dict):
                names.append((t.get("function") or {}).get("name", "?"))
            else:
                names.append(getattr(t, "name", getattr(t, "__name__", "?")))
        self.seen_tools = names
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls += 1
        sys_msgs = [m for m in messages if m.type == "system"]
        self.seen_system = content_text(sys_msgs[0].content) if sys_msgs else ""
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="done"))]
        )


def state_props(agent):
    """从输出 JSON Schema 里读状态字段名（不依赖某次运行是否真的写了 todos）。"""
    try:
        schema = agent.get_output_jsonschema()
        return sorted((schema.get("properties") or {}).keys())
    except Exception as e:  # noqa: BLE001
        return [f"<schema unavailable: {type(e).__name__}: {e}>"]


def probe(label, **kwargs):
    spy = SpyModel()
    from deepagents import create_deep_agent

    agent = create_deep_agent(model=spy, **kwargs)
    state = agent.invoke({"messages": [{"role": "user", "content": "hi"}]})
    props = state_props(agent)
    return {
        "label": label,
        "tool_count": len(spy.seen_tools),
        "tools": spy.seen_tools,
        "has_write_todos": "write_todos" in spy.seen_tools,
        "system_chars": len(spy.seen_system),
        "system_head": spy.seen_system[:160],
        "run_state_keys": sorted(state.keys()),
        "schema_props": props,
        "schema_has_todos": "todos" in props,
    }


def main():
    out = {"env": {}}
    import importlib.metadata as md

    for p in ["deepagents", "langchain", "langgraph"]:
        out["env"][p] = md.version(p)

    out["default"] = probe("default")

    from langchain.agents.middleware import TodoListMiddleware

    out["with_todo"] = probe("with_todo", middleware=[TodoListMiddleware()])

    d, w = out["default"], out["with_todo"]
    out["diff"] = {
        "tools_added": [t for t in w["tools"] if t not in d["tools"]],
        "system_chars_delta": w["system_chars"] - d["system_chars"],
        "schema_props_delta": [p for p in w["schema_props"] if p not in d["schema_props"]],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    dest = os.environ.get("OUT", "/tmp/ch04_probe.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n[saved] {dest}", file=sys.stderr)


if __name__ == "__main__":
    main()
