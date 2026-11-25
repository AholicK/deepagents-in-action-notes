"""ch04 实验 3（任务②③）：官方示例 —— 三大 Harness 框架对比 + LangSmith Trace + 复盘。

任务原文（第 4 章代码实战）：
  "请调研 Agent 开发领域的三大 Harness 框架（Deep Agents、Claude Agent SDK、Codex SDK），
   对比它们的核心能力差异，写一份简要分析报告。"
system_prompt 也用原文（不额外加强制规划指令），这样才能看出「官方示例到底会不会规划」。

跑完自动做三件复盘：
  1. result.get("todos", []) 最终状态统计
  2. 本地工具调用序列 vs LangSmith trace 里的 run 树
  3. 报告覆盖度：三个框架是否都被写到、是否有对比结构
"""
import json
import os
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from common import build_model, build_search, print_timeline, run_and_record  # noqa: E402

from deepagents import create_deep_agent  # noqa: E402
from langchain.agents.middleware import TodoListMiddleware  # noqa: E402

TASK = (
    "请调研 Agent 开发领域的三大 Harness 框架（Deep Agents、Claude Agent SDK、Codex SDK），"
    "对比它们的核心能力差异，写一份简要分析报告。"
)

SYSTEM = """你是一位专业的技术研究员。
面对复杂研究任务时，你会：
1. 先用 write_todos 制定研究计划
2. 逐步执行每个步骤，及时更新进度
3. 将搜索结果写入文件系统整理
4. 最终输出完整的研究报告
"""

FRAMEWORKS = ["Deep Agents", "Claude Agent SDK", "Codex SDK"]


def trace_lookup(project: str, since_s: float):
    """从 LangSmith 取最近一次 trace 的 id / url / run 树统计。"""
    try:
        from langsmith import Client

        c = Client()
        proj = None
        for p in c.list_projects(limit=100):
            if p.name == project:
                proj = p
                break
        runs = list(
            c.list_runs(
                project_name=project,
                is_root=True,
                limit=5,
                start_time=None,
            )
        )
        if not runs:
            return {"error": "no root runs found"}
        run = runs[0]
        trace_id = str(run.trace_id)
        run_id = str(run.id)
        children = list(c.list_runs(project_name=project, trace_id=trace_id, limit=200))
        kinds = {}
        for r in children:
            kinds[r.run_type] = kinds.get(r.run_type, 0) + 1
        tool_runs = [
            {"name": r.name, "type": r.run_type, "status": str(r.status)}
            for r in children
            if r.run_type in ("tool", "llm")
        ]
        org_id = getattr(proj, "tenant_id", None) if proj else None
        url = None
        if org_id:
            url = (
                f"https://smith.langchain.com/o/{org_id}/projects/p/{project}/"
                f"r/{run_id}?trace={trace_id}"
            )
        return {
            "run_id": run_id,
            "trace_id": trace_id,
            "url": url,
            "project": project,
            "run_types": kinds,
            "runs": tool_runs[:80],
        }
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def coverage_check(report: str, todos: list):
    hit = {fw: (fw.lower() in report.lower()) for fw in FRAMEWORKS}
    todo_hits = []
    for t in todos:
        c = t.get("content", "")
        # 清单项是否在报告里有对应内容：取前 8 个字符做粗匹配
        key = c[:8]
        todo_hits.append({"todo": c[:40], "status": t.get("status"), "mentioned": key in report})
    has_table = "|" in report and report.count("|") >= 6
    return {
        "frameworks_in_report": hit,
        "all_frameworks_present": all(hit.values()),
        "todo_items_mentioned": todo_hits,
        "has_table": has_table,
        "report_chars": len(report),
    }


def main():
    model_name = os.environ.get("MODEL") or "deepseek-v4-pro"
    agent = create_deep_agent(
        model=build_model(model_name),
        tools=[build_search(max_results=3)],
        middleware=[TodoListMiddleware()],
        system_prompt=SYSTEM,
    )
    out = os.environ.get("OUT", "./03_harness_result.json")
    rec = run_and_record(agent, TASK, out)
    rec["model"] = model_name
    rec["coverage"] = coverage_check(rec["final_report"], rec["final_todos"])
    rec["todo_stats"] = {
        s: sum(1 for t in rec["final_todos"] if t.get("status") == s)
        for s in ("pending", "in_progress", "completed")
    }
    rec["trace"] = trace_lookup(os.environ.get("LANGSMITH_PROJECT", "deepagents-course"), rec["elapsed_s"])
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)

    print_timeline(rec)
    print("\n[coverage]", json.dumps(rec["coverage"], ensure_ascii=False, indent=2))
    print("\n[todo_stats]", rec["todo_stats"])
    print("\n[trace]", json.dumps(rec["trace"], ensure_ascii=False, indent=2)[:1500])


if __name__ == "__main__":
    main()
