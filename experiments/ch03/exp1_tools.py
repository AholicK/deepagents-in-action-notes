"""实验 1：把 7 个内置文件工具全跑一遍。

对应验收 ①「用一次文件工具」——这里是 7 个全用，而且全部走真实执行路径：
模型（脚本）发出 tool_call → FilesystemMiddleware 的 ToolNode 执行 → StateBackend 读写 state。

跑法（WSL，项目根目录）：
    .venv/bin/python experiments/ch03/exp1_tools.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _scripted import ScriptedChatModel, call, say  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402

from deepagents import create_deep_agent  # noqa: E402

NOTE = """# Task3 实验笔记

## 虚拟文件系统
Agent 不把所有信息塞进 prompt，而是把资料存进文件、按需读取、搜索定位。

## 三个后端
- StateBackend：草稿纸，文件活在 state 里
- FilesystemBackend：真磁盘，落盘就能被别人看到
- StoreBackend：跨会话记忆库，换线程还在

## 待办
TODO: 补一张后端对比表
"""

model = ScriptedChatModel(
    script=[
        call("write_file", "c1", file_path="/notes/task3.md", content=NOTE),
        call("read_file", "c2", file_path="/notes/task3.md"),
        call(
            "edit_file",
            "c3",
            file_path="/notes/task3.md",
            old_string="TODO: 补一张后端对比表",
            new_string="TODO: 已完成（见 exp3_backends.py）",
        ),
        call("grep", "c4", pattern="Backend", output_mode="content"),
        call("glob", "c5", pattern="**/*.md"),
        call("ls", "c6", path="/notes"),
        call("delete", "c7", file_path="/notes/task3.md"),
        say("七个工具都跑完了。"),
    ]
)

agent = create_deep_agent(model=model, system_prompt="你是一个用来做文件工具实验的 Agent。")

# 用 stream 拿每一步之后的完整 state，看 files 键怎么变
snapshots = []
final = None
for chunk in agent.stream(
    {"messages": [HumanMessage(content="按剧本依次调用七个文件工具")]},
    stream_mode="values",
):
    final = chunk
    snapshots.append(
        {
            "消息数": len(chunk.get("messages", [])),
            "files": list(chunk.get("files", {}).keys()),
        }
    )

result = final

out = {
    "实验": "exp1 七个内置文件工具",
    "默认绑定工具": model.captured_tools,
    "工具数量": len(model.captured_tools),
    "步骤": [],
    "files 变化轨迹": snapshots,
}

for m in result["messages"]:
    if isinstance(m, AIMessage) and m.tool_calls:
        tc = m.tool_calls[0]
        out["步骤"].append({"工具": tc["name"], "入参": tc["args"]})
    elif isinstance(m, ToolMessage):
        content = m.content if isinstance(m.content, str) else json.dumps(m.content, ensure_ascii=False)
        out["步骤"][-1]["返回"] = content[:700]
        out["步骤"][-1]["返回长度"] = len(content)

out["最终回答"] = result["messages"][-1].content
out["state 里的 files 键"] = list(result.get("files", {}).keys())

print(json.dumps(out, ensure_ascii=False, indent=2))

Path(__file__).parent.joinpath("results").mkdir(exist_ok=True)
Path(__file__).parent.joinpath("results/exp1_tools.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
