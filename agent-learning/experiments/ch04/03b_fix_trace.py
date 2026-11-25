"""补查 LangSmith trace（不重跑 agent）。

修 03 里的两个问题：
1. list_runs(limit=200) 超过 API 上限 100 -> 改 100 并分页
2. coverage 的 todo 匹配用「前 8 字符」太粗 -> 改成实体/关键词匹配
"""
import json
import os
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.environ.get("COURSE_ENV", "/home/aholick/projects/research_deepagent/.env"), override=True)

RESULT = "./03_harness_result.json"


def fetch_trace(project: str):
    from langsmith import Client

    c = Client()
    org_id = None
    for p in c.list_projects(limit=50):
        if p.name == project:
            org_id = getattr(p, "tenant_id", None)
            break
    roots = list(c.list_runs(project_name=project, is_root=True, limit=5))
    if not roots:
        return {"error": "no root runs"}
    run = roots[0]
    trace_id, run_id = str(run.trace_id), str(run.id)
    children = list(c.list_runs(project_name=project, trace_id=trace_id, limit=100))
    kinds = {}
    for r in children:
        kinds[r.run_type] = kinds.get(r.run_type, 0) + 1
    tools = [r.name for r in children if r.run_type == "tool"]
    llm = [r for r in children if r.run_type == "llm"]
    llm_ms = []
    for r in llm:
        if r.end_time and r.start_time:
            llm_ms.append((r.end_time - r.start_time).total_seconds())
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
        "root_status": str(run.status),
        "run_types": kinds,
        "tool_runs": tools,
        "llm_count": len(llm),
        "llm_total_s": round(sum(llm_ms), 1),
        "llm_max_s": round(max(llm_ms), 1) if llm_ms else None,
    }


def coverage_v2(report: str, todos: list):
    ents = ["Deep Agents", "Claude Agent SDK", "Codex SDK"]
    hit = {e: (e.lower() in report.lower()) for e in ents}
    return {
        "frameworks": hit,
        "all_present": all(hit.values()),
        "has_table": report.count("|") >= 6,
        "has_selection_advice": "选型" in report or "推荐" in report,
        "has_conclusion": "小结" in report or "总结" in report,
        "report_chars": len(report),
        "todos_all_completed": all(t.get("status") == "completed" for t in todos) if todos else None,
    }


def main():
    d = json.load(open(RESULT, encoding="utf-8"))
    project = os.environ.get("LANGSMITH_PROJECT", "deepagents-course")
    d["trace"] = fetch_trace(project)
    d["coverage_v2"] = coverage_v2(d["final_report"], d["final_todos"])
    json.dump(d, open(RESULT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(d["trace"], ensure_ascii=False, indent=2))
    print("\ncoverage_v2:", json.dumps(d["coverage_v2"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
