"""实验 2：大结果自动卸载（Context Eviction）。

对应验收 ②「亲眼见证一次大结果自动卸载」。

三个动作：
  A. 自定义工具 huge_dump 返回 ~130k 字符（≈32k tokens > 20k 阈值）
     → 看 ToolMessage 变成了什么（文件路径 + 首尾 5 行预览）
  B. 同一线程里 read_file 把卸载掉的内容读回来
  C. 对照组：write_file 写一个同样大的文件，再 read_file 整读
     → 内置文件工具在豁免名单里，不会被卸载

跑法（WSL，项目根目录）：
    .venv/bin/python experiments/ch03/exp2_eviction.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _scripted import ScriptedChatModel, call, say  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

from deepagents import create_deep_agent  # noqa: E402

BIG_LINES = 2000
BIG_CHARS_PER_LINE = 60


@tool
def huge_dump(lines: int = BIG_LINES) -> str:
    """Dump a large synthetic report. Used to trigger context eviction."""
    return "\n".join(
        f"line {i:05d} | " + ("x" * BIG_CHARS_PER_LINE) for i in range(lines)
    )


BIG_CONTENT = "\n".join(
    f"line {i:05d} | " + ("x" * BIG_CHARS_PER_LINE) for i in range(BIG_LINES)
)


def tool_messages(result) -> list[ToolMessage]:
    return [m for m in result["messages"] if isinstance(m, ToolMessage)]


def text_of(m: ToolMessage) -> str:
    return m.content if isinstance(m.content, str) else json.dumps(m.content, ensure_ascii=False)


out = {
    "实验": "exp2 大结果自动卸载",
    "原始大结果字符数": len(BIG_CONTENT),
    "估算 token 数(÷4)": len(BIG_CONTENT) // 4,
    "默认卸载阈值 token": 20000,
}

saver = MemorySaver()
cfg = {"configurable": {"thread_id": "exp2-eviction"}}

# ---------- A. 触发卸载 ----------
m1 = ScriptedChatModel(
    script=[call("huge_dump", "c1", lines=BIG_LINES), say("dump 完了")]
)
agent = create_deep_agent(
    model=m1,
    tools=[huge_dump],
    system_prompt="你是上下文卸载实验的 Agent。",
    checkpointer=saver,
)
r1 = agent.invoke({"messages": [HumanMessage(content="调 huge_dump")]}, cfg)

dump_msg = tool_messages(r1)[-1]
dump_text = text_of(dump_msg)
out["A_卸载后返回字符数"] = len(dump_text)
out["A_是否被卸载"] = "Tool result too large" in dump_text
out["A_卸载后前 900 字符"] = dump_text[:900]

m = re.search(r"saved in the filesystem at this path:\s*(\S+)", dump_text)
evicted_path = m.group(1) if m else None
out["A_卸载落盘路径"] = evicted_path
out["A_state 里的 files"] = list(r1.get("files", {}).keys())
out["A_预览里是否出现截断标记"] = "lines truncated" in dump_text

# ---------- B. 读回 ----------
if evicted_path:
    m2 = ScriptedChatModel(
        script=[
            call("read_file", "c2", file_path=evicted_path, offset=0, limit=5),
            say("读回来了"),
        ]
    )
    agent2 = create_deep_agent(
        model=m2,
        tools=[huge_dump],
        system_prompt="你是上下文卸载实验的 Agent。",
        checkpointer=saver,
    )
    r2 = agent2.invoke({"messages": [HumanMessage(content="把卸载的文件读回来")]}, cfg)
    back = tool_messages(r2)[-1]
    out["B_读回成功"] = "line 00000" in text_of(back)
    out["B_读回内容前 300 字符"] = text_of(back)[:300]

# ---------- C. 对照组：内置 read_file 不卸载 ----------
m3 = ScriptedChatModel(
    script=[
        call("write_file", "c3", file_path="/big/raw.md", content=BIG_CONTENT),
        call("read_file", "c4", file_path="/big/raw.md", offset=0, limit=BIG_LINES + 100),
        say("对照组完成"),
    ]
)
agent3 = create_deep_agent(
    model=m3,
    tools=[huge_dump],
    system_prompt="你是上下文卸载实验的 Agent。",
    checkpointer=MemorySaver(),
)
r3 = agent3.invoke(
    {"messages": [HumanMessage(content="写一个大文件然后整读")]},
    {"configurable": {"thread_id": "exp2-control"}},
)
tms = tool_messages(r3)
read_msg = tms[-1]
read_text = text_of(read_msg)
out["C_对照组 read_file 返回字符数"] = len(read_text)
out["C_对照组是否被卸载"] = "Tool result too large" in read_text
out["C_对照组是否读到全文"] = "line 01999" in read_text
out["C_对照组尾部 400 字符"] = read_text[-400:]
out["C_对照组说明"] = (
    "read_file 在豁免名单里，不会被卸载成文件引用；"
    "但它用同一个 20000 token 预算（=80000 字符）做原地分页截断，"
    "返回的是截断提示 + next_offset，不是全文。"
)

print(json.dumps(out, ensure_ascii=False, indent=2))

Path(__file__).parent.joinpath("results").mkdir(exist_ok=True)
Path(__file__).parent.joinpath("results/exp2_eviction.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
