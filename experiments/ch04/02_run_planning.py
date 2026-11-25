"""ch04 实验 2（任务①）：显式启用规划，跑一个多步研究任务，观察 pending → in_progress → completed。

对照课程原文的 system_prompt（第 4 章代码实战）：
  1. 先用 write_todos 制定研究计划
  2. 逐步执行每个步骤，及时更新进度
  3. 将搜索结果写入文件系统整理
  4. 最终输出完整的研究报告
"""
import json
import os
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from common import build_model, build_search, print_timeline, run_and_record  # noqa: E402

from deepagents import create_deep_agent  # noqa: E402
from langchain.agents.middleware import TodoListMiddleware  # noqa: E402

TASK = (
    "写一份《Agent 上下文工程三种做法对比》报告，按这 5 步做：\n"
    "1. 调研 Deep Agents 的虚拟文件系统（FilesystemMiddleware / StateBackend）\n"
    "2. 调研 Claude Code 的 CLAUDE.md 记忆机制\n"
    "3. 调研 OpenAI Agents SDK 的 session / 记忆管理\n"
    "4. 把三部分要点先整理进文件 /notes.md\n"
    "5. 输出 800 字左右对比报告，含一个对比表格\n"
    "先列完整计划再执行；搜索最多 5 次。"
)

SYSTEM = """你是一位专业的技术研究员。工作规则：
1. 任何包含 3 个以上子任务的工作，第一步必须调用 write_todos，把所有步骤以 pending 状态列出来，再开始执行。
2. 每完成一个步骤，立刻调用 write_todos 把该步骤标为 completed，并把正在做的下一步标为 in_progress。
3. 搜索到的资料先写入文件系统整理，再写最终报告。
4. 最终报告必须覆盖清单里的每一项。
"""


def main():
    model_name = os.environ.get("MODEL") or None
    agent = create_deep_agent(
        model=build_model(model_name),
        tools=[build_search(max_results=3)],
        middleware=[TodoListMiddleware()],
        system_prompt=SYSTEM,
    )
    out = os.environ.get("OUT", "./02_planning_result.json")
    rec = run_and_record(agent, TASK, out)
    rec["model"] = model_name or os.environ.get("AGENTSEEK_MODEL")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    print_timeline(rec)
    print("\n[final_todos]", json.dumps(rec["final_todos"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
