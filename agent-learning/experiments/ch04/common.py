"""ch04 实验公共件：模型、搜索工具、清单流转记录器。

环境沿用 Task1-3 的 research_deepagent 项目（WSL2，deepagents 0.7.8）。
密钥从该项目的 .env 读取，不写进仓库。
"""
import json
import os
import time

from dotenv import load_dotenv

ENV_PATH = os.environ.get(
    "COURSE_ENV", "/home/aholick/projects/research_deepagent/.env"
)
load_dotenv(ENV_PATH, override=True)


def build_model(model: str | None = None):
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model or os.environ.get("AGENTSEEK_MODEL", "deepseek-v4.1-flash"),
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ["OPENAI_API_BASE"],
        temperature=0,
        timeout=180,
        max_retries=2,
    )


def build_search(max_results: int = 3):
    from tavily import TavilyClient

    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

    def internet_search(query: str, max_results_n: int = max_results) -> dict:
        """搜索互联网获取最新信息。

        Args:
            query: 搜索关键词，用自然语言描述要查的内容。
            max_results_n: 返回结果条数，默认 3。
        """
        res = client.search(query, max_results=max_results_n)
        items = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": (r.get("content") or "")[:800],
            }
            for r in res.get("results", [])
        ]
        return {"query": query, "results": items}

    return internet_search


def run_and_record(agent, task: str, out_path: str, recursion_limit: int = 150):
    """跑一次任务，逐步记录 todos 快照与工具调用序列，落盘 JSON。"""
    t0 = time.time()
    snapshots = []
    last_todos = None
    msg_count = 0
    tool_calls = []
    final_state = None

    for chunk in agent.stream(
        {"messages": [{"role": "user", "content": task}]},
        stream_mode="values",
        config={"recursion_limit": recursion_limit},
    ):
        final_state = chunk
        todos = chunk.get("todos")
        if todos != last_todos:
            snapshots.append(
                {
                    "at_step": len(snapshots),
                    "elapsed_s": round(time.time() - t0, 1),
                    "todos": todos,
                }
            )
            last_todos = todos

        msgs = chunk.get("messages", [])
        for m in msgs[msg_count:]:
            for tc in getattr(m, "tool_calls", None) or []:
                tool_calls.append(
                    {
                        "elapsed_s": round(time.time() - t0, 1),
                        "name": tc.get("name"),
                        "args": tc.get("args"),
                    }
                )
        msg_count = len(msgs)

    elapsed = round(time.time() - t0, 1)
    final_msgs = (final_state or {}).get("messages", [])
    report = ""
    for m in reversed(final_msgs):
        if getattr(m, "type", "") == "ai" and (m.content or "").strip():
            report = m.content if isinstance(m.content, str) else str(m.content)
            break

    record = {
        "task": task,
        "elapsed_s": elapsed,
        "llm_calls": sum(1 for m in final_msgs if getattr(m, "type", "") == "ai"),
        "tool_call_count": len(tool_calls),
        "tool_call_names": [t["name"] for t in tool_calls],
        "tool_calls": tool_calls,
        "todo_snapshots": snapshots,
        "final_todos": (final_state or {}).get("todos", []),
        "final_report": report,
        "report_chars": len(report),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return record


def print_timeline(record):
    print(f"\n=== {record['task'][:60]} ===")
    print(f"耗时 {record['elapsed_s']}s | AI 消息 {record['llm_calls']} 条 | 工具调用 {record['tool_call_count']} 次")
    print("工具序列:", " → ".join(record["tool_call_names"]))
    print("\n清单快照:")
    for s in record["todo_snapshots"]:
        todos = s["todos"] or []
        print(f"  [t={s['elapsed_s']}s] " + " | ".join(
            f"{t.get('status')}:{t.get('content','')[:24]}" for t in todos
        ) if todos else f"  [t={s['elapsed_s']}s] <无 todos>")
    print(f"\n最终报告 {record['report_chars']} 字符，开头：\n{record['final_report'][:300]}")
