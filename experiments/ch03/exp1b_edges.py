"""实验 1b：v0.7 的四个边界，课程提到但没有给实测值。

  1. 空目录 ls / 空 glob 返回什么
  2. grep 三种 output_mode 的真实差异
  3. grep 超过 1000 匹配时的 truncated 提示
  4. write_file 是「完整覆盖」还是「追加」（v0.7 提醒）
  5. FilesystemBackend virtual_mode=True 能不能挡住 ../ 越界

跑法（WSL，项目根目录）：
    .venv/bin/python experiments/ch03/exp1b_edges.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _scripted import ScriptedChatModel, call, say  # noqa: E402
from langchain_core.messages import HumanMessage, ToolMessage  # noqa: E402

from deepagents import create_deep_agent  # noqa: E402
from deepagents.backends import FilesystemBackend  # noqa: E402


def run(script: list, **agent_kwargs):
    model = ScriptedChatModel(script=script + [say("done")])
    agent = create_deep_agent(model=model, system_prompt="边界实验。", **agent_kwargs)
    return agent.invoke({"messages": [HumanMessage(content="执行")]})


def tool_texts(result) -> list[tuple[str, str]]:
    """按顺序返回 (工具名, 返回文本)。"""
    out = []
    for m in result["messages"]:
        if isinstance(m, ToolMessage):
            c = m.content if isinstance(m.content, str) else json.dumps(m.content, ensure_ascii=False)
            out.append((m.name or "?", c))
    return out


out: dict = {"实验": "exp1b v0.7 边界实测"}

# ---------- 1. 空目录 / 空 glob ----------
r = run([call("ls", "e1", path="/empty"), call("glob", "e2", pattern="**/*.txt")])
for name, text in tool_texts(r):
    out[f"1_空_{name}"] = text

# ---------- 2. grep 三种模式 ----------
FILES = {
    "/proj/a.py": "def create_agent():\n    pass\n\n# TODO: 加日志\ndef helper():\n    pass\n",
    "/proj/b.py": "def create_agent():\n    return 1\n\n# TODO: 补测试\n",
    "/proj/c.md": "create_agent 在文档里也出现了一次\n",
}
script = [call("write_file", f"w{i}", file_path=p, content=c) for i, (p, c) in enumerate(FILES.items())]
script += [
    call("grep", "g1", pattern="create_agent", output_mode="files_with_matches"),
    call("grep", "g2", pattern="create_agent", output_mode="content"),
    call("grep", "g3", pattern="create_agent", output_mode="count"),
    call("grep", "g4", pattern="TODO", glob="*.py", output_mode="content"),
]
r = run(script)
grep_results = [(n, t) for n, t in tool_texts(r) if n == "grep"]
for i, (name, text) in enumerate(grep_results):
    out[f"2_grep_{i+1}"] = {"模式": ["files_with_matches", "content", "count", "content+glob"][i], "返回": text}

# ---------- 3. grep 超过 1000 匹配 ----------
many = "\n".join(f"needle line {i}" for i in range(1500))
r = run(
    [
        call("write_file", "m1", file_path="/big/many.txt", content=many),
        call("grep", "m2", pattern="needle", output_mode="count"),
        call("grep", "m3", pattern="needle", output_mode="files_with_matches"),
    ]
)
texts = [t for n, t in tool_texts(r) if n == "grep"]
out["3_1500个匹配_count"] = texts[0]
out["3_1500个匹配_files"] = texts[1][:300]

# ---------- 4. write_file 覆盖语义 ----------
r = run(
    [
        call("write_file", "o1", file_path="/ov.txt", content="第一版\n第二行\n第三行\n"),
        call("write_file", "o2", file_path="/ov.txt", content="只有一行\n"),
        call("read_file", "o3", file_path="/ov.txt"),
    ]
)
texts = [t for n, t in tool_texts(r)]
out["4_覆盖写_第二次返回"] = texts[1]
out["4_覆盖写_读回内容"] = texts[2]

# ---------- 5. FilesystemBackend 越界 ----------
ROOT = Path("/tmp/ch03_virtual_root")
shutil.rmtree(ROOT, ignore_errors=True)
ROOT.mkdir(parents=True)
(ROOT / "inside.txt").write_text("root 内的文件", encoding="utf-8")
Path("/tmp/ch03_outside_secret.txt").write_text("root 外的秘密", encoding="utf-8")

r = run(
    [
        call("read_file", "v1", file_path="/inside.txt"),
        call("read_file", "v2", file_path="/../ch03_outside_secret.txt"),
        call("write_file", "v3", file_path="/../ch03_escape.txt", content="越界写"),
    ],
    backend=FilesystemBackend(root_dir=str(ROOT), virtual_mode=True),
)
for i, (n, t) in enumerate(tool_texts(r)):
    out[f"5_越界_{i+1}_{n}"] = t[:220]
out["5_越界文件是否被创建"] = Path("/tmp/ch03_escape.txt").exists()

print(json.dumps(out, ensure_ascii=False, indent=2))

Path(__file__).parent.joinpath("results").mkdir(exist_ok=True)
Path(__file__).parent.joinpath("results/exp1b_edges.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
