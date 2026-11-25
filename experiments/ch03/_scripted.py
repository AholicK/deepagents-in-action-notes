"""ScriptedChatModel —— 按预设脚本逐条返回 AIMessage 的假模型。

用途：把「模型要做什么」写死，只让 **工具执行 / 中间件 / 后端** 这三层真跑。
这样每次实验结果完全可复现，不花 token，也不受模型随机性影响。

它同时记录了模型在真实 bind_tools 时收到的工具清单，
用来回答「默认到底给了 Agent 几个工具」这种问题。
"""

from __future__ import annotations

from typing import Any, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from pydantic import Field


class ScriptedChatModel(BaseChatModel):
    """按 script 顺序吐出消息；脚本用完就回一句 [script exhausted]。"""

    script: list = Field(default_factory=list)
    calls: int = 0
    captured_tools: list = Field(default_factory=list)
    captured_messages: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    # deepagents 在构造图时会对模型 bind_tools；这里原样返回 self，
    # 但把工具名抄下来，方便断言「默认绑了几个工具」。
    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":
        self.captured_tools = [
            t.name if isinstance(t, BaseTool) else getattr(t, "name", str(t))
            for t in tools
        ]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.captured_messages.append(list(messages))
        idx = self.calls
        self.calls += 1
        if idx < len(self.script):
            msg = self.script[idx]
        else:
            msg = AIMessage(content="[script exhausted]")
        return ChatResult(generations=[ChatGeneration(message=msg)])

    # 同一个模型实例要在多轮实验里复用，就靠 reset 换剧本
    def reset(self, script: list) -> None:
        self.script = list(script)
        self.calls = 0


def call(name: str, call_id: str, **args) -> AIMessage:
    """构造一条「模型要求调某个工具」的 AIMessage。"""
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


def say(text: str) -> AIMessage:
    """构造一条普通回复（不带工具调用）—— 循环到此结束。"""
    return AIMessage(content=text)
