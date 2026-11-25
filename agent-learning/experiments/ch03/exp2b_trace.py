"""实验 2b：带 LangSmith tracing 跑一次「大结果卸载」，拿到可点开的 trace。

对应验收 ② 里「在 LangSmith Trace 里看到它被转成文件引用 + 首尾预览」。

跑法（WSL，项目根目录，需要 .env 里 LANGSMITH_TRACING=true）：
    .venv/bin/python experiments/ch03/exp2b_trace.py

会打印 run_id 和 trace 链接。
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv  # noqa: E402

# 必须在 import deepagents / langchain 之前加载，tracing 才读得到环境变量
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from _scripted import ScriptedChatModel, call, say  # noqa: E402
from langchain_core.messages import HumanMessage, ToolMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402

from deepagents import create_deep_agent  # noqa: E402

BIG_LINES = 2000


@tool
def huge_dump(lines: int = BIG_LINES) -> str:
    """Dump a large synthetic report. Used to trigger context eviction."""
    return "\n".join(f"line {i:05d} | " + ("x" * 60) for i in range(lines))


run_id = uuid.uuid4()
cfg = {"configurable": {"thread_id": "exp2b-trace"}, "run_id": str(run_id)}

model = ScriptedChatModel(
    script=[call("huge_dump", "trace-call-1", lines=BIG_LINES), say("dump 完了")]
)
agent = create_deep_agent(
    model=model, tools=[huge_dump], system_prompt="上下文卸载 trace 实验。"
)
result = agent.invoke({"messages": [HumanMessage(content="调 huge_dump")]}, cfg)

tms = [m for m in result["messages"] if isinstance(m, ToolMessage)]
text = tms[-1].content if isinstance(tms[-1].content, str) else ""

out = {
    "run_id": str(run_id),
    "project": "deepagents-course",
    "卸载后字符数": len(text),
    "是否卸载": "Tool result too large" in text,
    "落盘路径": text.split("saved in the filesystem at this path:")[-1].split("\n")[0].strip()
    if "saved in the filesystem" in text
    else None,
    "trace_url_模板": f"https://smith.langchain.com/projects/p/deepagents-course/r/{run_id}",
}
print(json.dumps(out, ensure_ascii=False, indent=2))
