"""实验 3：四种 Backend 对比 —— 文件到底存哪、换线程/换进程还在不在。

对应验收 ③「至少两种 Backend 的对比实验」。这里做四种：

  1. StateBackend（默认）     → 文件在 LangGraph state，同 thread 在，新 thread 不在
  2. FilesystemBackend        → 文件落到 WSL 磁盘，进程重启也在
  3. StoreBackend             → 文件在 BaseStore，跨 thread 在；store 实例一换就没了
  4. CompositeBackend         → /memories/ 走 Store，其他走 State（路径前缀路由）

跑法（WSL，项目根目录）：
    .venv/bin/python experiments/ch03/exp3_backends.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _scripted import ScriptedChatModel, call, say  # noqa: E402
from langchain_core.messages import HumanMessage, ToolMessage  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.store.memory import InMemoryStore  # noqa: E402

from deepagents import create_deep_agent  # noqa: E402
from deepagents.backends import (  # noqa: E402
    CompositeBackend,
    FilesystemBackend,
    StateBackend,
    StoreBackend,
)

FS_ROOT = Path("/tmp/ch03_fs_root")


def last_tool_text(result) -> str:
    tms = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    if not tms:
        return ""
    m = tms[-1]
    return m.content if isinstance(m.content, str) else json.dumps(m.content, ensure_ascii=False)


def write_agent(model_kwargs: dict, **agent_kwargs):
    """造一个「写一个文件」的 agent。"""
    model = ScriptedChatModel(
        script=[
            call("write_file", "w1", file_path=agent_kwargs.pop("_path"), content=agent_kwargs.pop("_content")),
            say("写完了"),
        ]
    )
    return create_deep_agent(model=model, system_prompt="后端对比实验。", **agent_kwargs)


def read_agent(path: str, **agent_kwargs):
    """造一个「读一个文件」的 agent。"""
    model = ScriptedChatModel(
        script=[call("read_file", "r1", file_path=path), say("读完了")]
    )
    return create_deep_agent(model=model, system_prompt="后端对比实验。", **agent_kwargs)


out = {"实验": "exp3 四种 Backend 对比", "场景": {}}

# ============================================================
# 1. StateBackend（默认）
# ============================================================
saver = MemorySaver()
cfg_a = {"configurable": {"thread_id": "thread-A"}}
cfg_b = {"configurable": {"thread_id": "thread-B"}}

a1 = write_agent({}, checkpointer=saver, _path="/memo.txt", _content="state 里的 hello")
a1.invoke({"messages": [HumanMessage(content="写")]}, cfg_a)

same = read_agent("/memo.txt", checkpointer=saver).invoke(
    {"messages": [HumanMessage(content="读")]}, cfg_a
)
other = read_agent("/memo.txt", checkpointer=saver).invoke(
    {"messages": [HumanMessage(content="读")]}, cfg_b
)

out["场景"]["1_StateBackend"] = {
    "存哪": "LangGraph agent state 的 files 键（内存/checkpointer）",
    "同 thread 换 agent 实例能读到": "state 里的 hello" in last_tool_text(same),
    "同 thread 读回内容": last_tool_text(same)[:200],
    "新 thread 能读到": "state 里的 hello" in last_tool_text(other),
    "新 thread 读回内容": last_tool_text(other)[:200],
}

# ============================================================
# 2. FilesystemBackend（真磁盘）
# ============================================================
shutil.rmtree(FS_ROOT, ignore_errors=True)
FS_ROOT.mkdir(parents=True, exist_ok=True)

fs_backend = FilesystemBackend(root_dir=str(FS_ROOT), virtual_mode=True)
a2 = write_agent({}, backend=fs_backend, _path="/memo.txt", _content="磁盘上的 hello")
a2.invoke(
    {"messages": [HumanMessage(content="写")]},
    {"configurable": {"thread_id": "fs-thread-1"}},
)

disk_file = FS_ROOT / "memo.txt"
# 新 agent + 新线程 + 新 backend 实例，只有磁盘是共享的
fs_backend2 = FilesystemBackend(root_dir=str(FS_ROOT), virtual_mode=True)
read_back = read_agent("/memo.txt", backend=fs_backend2).invoke(
    {"messages": [HumanMessage(content="读")]},
    {"configurable": {"thread_id": "fs-thread-2"}},
)

out["场景"]["2_FilesystemBackend"] = {
    "存哪": f"真磁盘：{FS_ROOT}",
    "磁盘上文件存在": disk_file.exists(),
    "磁盘上文件内容": disk_file.read_text(encoding="utf-8") if disk_file.exists() else None,
    "新 thread 新实例能读到": "磁盘上的 hello" in last_tool_text(read_back),
    "新 thread 读回内容": last_tool_text(read_back)[:200],
}

# ============================================================
# 3. StoreBackend（跨线程持久）
# ============================================================
store = InMemoryStore()


def ns(rt):
    """本地 invoke 时 rt.server_info 是 None，兜一个本地用户。"""
    info = getattr(rt, "server_info", None)
    if info is not None and getattr(info, "user", None) is not None:
        return (info.user.identity,)
    return ("local-user",)


st_backend = StoreBackend(namespace=ns)
a3 = write_agent({}, backend=st_backend, store=store, _path="/memo.txt", _content="store 里的 hello")
a3.invoke(
    {"messages": [HumanMessage(content="写")]},
    {"configurable": {"thread_id": "store-thread-1"}},
)

read_cross = read_agent("/memo.txt", backend=StoreBackend(namespace=ns), store=store).invoke(
    {"messages": [HumanMessage(content="读")]},
    {"configurable": {"thread_id": "store-thread-2"}},
)

# 模拟「进程重启」：换一个全新的 InMemoryStore
fresh_store = InMemoryStore()
read_fresh = read_agent("/memo.txt", backend=StoreBackend(namespace=ns), store=fresh_store).invoke(
    {"messages": [HumanMessage(content="读")]},
    {"configurable": {"thread_id": "store-thread-3"}},
)

out["场景"]["3_StoreBackend"] = {
    "存哪": "LangGraph BaseStore（这里用 InMemoryStore，生产换持久化实现）",
    "跨 thread 能读到": "store 里的 hello" in last_tool_text(read_cross),
    "跨 thread 读回内容": last_tool_text(read_cross)[:200],
    "换一个新 Store 实例(模拟重启)能读到": "store 里的 hello" in last_tool_text(read_fresh),
    "换新 Store 读回内容": last_tool_text(read_fresh)[:200],
}

# ============================================================
# 4. CompositeBackend（混合路由）
# ============================================================
store2 = InMemoryStore()
composite = CompositeBackend(
    default=StateBackend(),
    routes={"/memories/": StoreBackend(namespace=ns)},
)

model_w = ScriptedChatModel(
    script=[
        call("write_file", "w1", file_path="/workspace/plan.md", content="临时草稿"),
        call("write_file", "w2", file_path="/memories/pref.txt", content="长期偏好"),
        say("两个都写了"),
    ]
)
agent_w = create_deep_agent(
    model=model_w, system_prompt="混合路由实验。", backend=composite, store=store2
)
agent_w.invoke(
    {"messages": [HumanMessage(content="写两个文件")]},
    {"configurable": {"thread_id": "comp-1"}},
)

# 新线程：/workspace/plan.md 应该读不到，/memories/pref.txt 应该读得到
r_ws = read_agent(
    "/workspace/plan.md", backend=CompositeBackend(default=StateBackend(), routes={"/memories/": StoreBackend(namespace=ns)}), store=store2
).invoke({"messages": [HumanMessage(content="读")]}, {"configurable": {"thread_id": "comp-2"}})

r_mem = read_agent(
    "/memories/pref.txt", backend=CompositeBackend(default=StateBackend(), routes={"/memories/": StoreBackend(namespace=ns)}), store=store2
).invoke({"messages": [HumanMessage(content="读")]}, {"configurable": {"thread_id": "comp-3"}})

out["场景"]["4_CompositeBackend"] = {
    "规则": "default=StateBackend，/memories/ 前缀走 StoreBackend",
    "新 thread 读 /workspace/plan.md（State 路由）": last_tool_text(r_ws)[:160],
    "新 thread 读 /memories/pref.txt（Store 路由）": last_tool_text(r_mem)[:160],
    "State 路由的文件跨线程丢了": "临时草稿" not in last_tool_text(r_ws),
    "Store 路由的文件跨线程还在": "长期偏好" in last_tool_text(r_mem),
}

print(json.dumps(out, ensure_ascii=False, indent=2))

Path(__file__).parent.joinpath("results").mkdir(exist_ok=True)
Path(__file__).parent.joinpath("results/exp3_backends.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
