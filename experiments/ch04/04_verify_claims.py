"""ch04 实验 4：验证笔记/反馈里引用的两个硬事实。

A. write_todos 的真实 JSON Schema（status 是不是 enum）
B. Checkpointer + 同一 thread_id 是否真的能让第二次 invoke 看到上次的 todos

用 ScriptedChatModel（按剧本返回，零 token），保证可复现。
"""
import json
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field


class Scripted(BaseChatModel):
    script: list = Field(default_factory=list)
    idx: int = 0
    captured_tools: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        self.captured_tools = list(tools)
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        msg = (
            self.script[self.idx]
            if self.idx < len(self.script)
            else AIMessage(content="done")
        )
        self.idx += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])


def part_a_schema():
    from deepagents import create_deep_agent
    from langchain.agents.middleware import TodoListMiddleware

    spy = Scripted()
    agent = create_deep_agent(model=spy, tools=[], middleware=[TodoListMiddleware()])
    # bind_tools 发生在第一次 invoke 时，所以先跑一轮再读
    agent.invoke({"messages": [{"role": "user", "content": "hi"}]})
    target = [t for t in spy.captured_tools if getattr(t, "name", "") == "write_todos"]
    if not target:
        return {
            "error": "write_todos not found in bound tools",
            "captured_types": [type(t).__name__ for t in spy.captured_tools],
            "captured_names": [getattr(t, "name", None) for t in spy.captured_tools],
        }
    tool = target[0]
    out = {
        "description_head": (tool.description or "")[:300],
        "args_schema": None,
        "openai_tool": None,
    }
    try:
        out["args_schema"] = tool.args_schema.model_json_schema()
    except Exception as e:  # noqa: BLE001
        out["args_schema"] = f"<{type(e).__name__}: {e}>"
    try:
        out["openai_tool"] = convert_to_openai_tool(tool)
    except Exception as e:  # noqa: BLE001
        out["openai_tool"] = f"<{type(e).__name__}: {e}>"
    return out


def part_b_checkpointer():
    from deepagents import create_deep_agent
    from langchain.agents.middleware import TodoListMiddleware
    from langgraph.checkpoint.memory import InMemorySaver

    todos_payload = [
        {"content": "第一步：调研", "status": "completed"},
        {"content": "第二步：写报告", "status": "in_progress"},
    ]
    script = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "write_todos", "args": {"todos": todos_payload}, "id": "c1"}
            ],
        ),
        AIMessage(content="第一轮做完了"),
        AIMessage(content="第二轮开始"),
    ]
    model = Scripted(script=script)
    agent = create_deep_agent(
        model=model,
        tools=[],
        middleware=[TodoListMiddleware()],
        checkpointer=InMemorySaver(),
    )
    cfg = {"configurable": {"thread_id": "task4-verify"}}

    r1 = agent.invoke({"messages": [{"role": "user", "content": "开始"}]}, cfg)
    r2 = agent.invoke({"messages": [{"role": "user", "content": "继续"}]}, cfg)

    # 对照组：换一个 thread_id
    r3 = agent.invoke(
        {"messages": [{"role": "user", "content": "另一个线程"}]},
        {"configurable": {"thread_id": "task4-other"}},
    )
    return {
        "run1_todos": r1.get("todos", "<missing>"),
        "run1_messages": len(r1["messages"]),
        "run2_todos": r2.get("todos", "<missing>"),
        "run2_messages": len(r2["messages"]),
        "run3_other_thread_todos": r3.get("todos", "<missing>"),
        "run3_other_thread_messages": len(r3["messages"]),
    }


def main():
    out = {"A_schema": part_a_schema(), "B_checkpointer": part_b_checkpointer()}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    with open("./04_verify_result.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
