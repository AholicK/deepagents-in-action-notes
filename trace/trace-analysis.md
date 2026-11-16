# Trace 瓶颈分析

> trace_id: `01a1e46c-3547-7b10-bcca-4a9c7986215c`
> 项目：`deepagents-course` · 问题：*Research what LangGraph 1.0 added vs 0.x. Cite sources.*
> 模型：`deepseek-v4.1-flash` · 搜索：Tavily

## 一、总体

| 指标 | 数值 |
|---|---|
| 总耗时 | **313.49 s**（5 分 13 秒） |
| LLM 调用 | 46 个，合计 **275.8 s（88%）** |
| 工具调用 | 61 个（含 3 个 `task` 包装层） |
| 报告产出 | 12,440 字符，带编号引用 |

**第一个结论：88% 的时间花在模型生成上，不是网络、不是工具。**

## 二、层级结构（三件事不能混）

```
LangGraph (chain)                                   313.49s
├── PatchToolCallsMiddleware.before_agent (chain)     1ms
├── TodoListMiddleware.after_model (chain) ×27      ~0.5ms each
├── model (chain) [3.36s]
│   └── FilesystemMiddleware.awrap_model_call
│       └── SubAgentMiddleware.awrap_model_call
│           └── SummarizationMiddleware.awrap_model_call
│               └── TodoListMiddleware.awrap_model_call
│                   └── AnthropicPromptCachingMiddleware.awrap_model_call
│                       └── ChatOpenAI (llm) [3.35s]        ← 真正的模型调用
├── tools (chain)
│   └── tavily_search (tool)                                ← 真正的工具调用
└── task (tool) [107.39s]                                   ← 子 Agent 包装层，不是工具
```

**关键**：`model`、`tools`、`task` 都是 chain 或包装层，只有 `ChatOpenAI (llm)` 和 `tavily_search (tool)` 是真实叶子。把 `task` 当工具瓶颈会把子 Agent 内部的模型调用重复计算一遍。

## 三、模型瓶颈（run_type=llm）

| # | 耗时 | tokens | run_id | 说明 |
|---|---|---|---|---|
| 1 | **38.78s** | 80,090 | `01a1e46d-85d8-7973-9ec1-1cfd5a3f1b15` | 首 token 仅 1s，其余 37.8s 在生成；输出是「研究结论速览」→ 最终报告写作 |
| 2 | 37.60s | 55,388 | `01a1e46d-23d9-73e0-9ce5-064a83aa5dd1` | 长输出综合 |
| 3 | 26.17s | 29,839 | `01a1e46f-cd56-79d2-9d52-59e974487cb4` | |
| 4 | 24.46s | 68,211 | `01a1e46f-488e-7b61-...` | |
| 5 | 9.45s | 25,398 | `01a1e46f-a85e-7f83-...` | |

**前 4 名合计 127s，占 trace 总时长 40%。**

### 最慢那次的关键证据

```json
{
  "name": "ChatOpenAI",
  "duration_ms": 38780,
  "start_time": "2026-11-16T12:55:45",
  "first_token_time": "2026-11-16T12:55:46",
  "token_usage": { "total_tokens": 80090 },
  "outputs": { "generations": "finish_reason=stop, model=deepseek-v4.1-flash" }
}
```

**`start` → `first_token` 只差 1 秒，其余 37.8 秒全在吐字。**

这直接排除了「网络慢 / 排队慢 / 超时设置不当」三个假设——优化方向只能是**砍输入（80K tokens 太长）或缩短输出**。

## 四、工具瓶颈（排除 `task`）

| 工具 | 次数 | 累计耗时 | 最慢单次 |
|---|---|---|---|
| **`tavily_search`** | 26 | **195.24s** | **11.23s**（`01a1e46c-bb44-79e2-...`） |
| `grep` | 12 | 0.03s | — |
| `read_file` | 6 | 0.01s | — |
| `edit_file` | 5 | 0.00s | — |
| `write_file` | 2 | 0.00s | — |
| `write_todos` | 5 | 0.00s | — |
| `think_tool` | 2 | 0.01s | — |

**被排除的 `task` 包装层**（它们包含子 Agent 内部的模型和工具调用）：

| 耗时 | run_id |
|---|---|
| 107.39s | `01a1e46c-7a1c-7720-...` |
| 94.45s | `01a1e46e-375a-74b1-...` |
| 81.11s | `01a1e46c-7a1e-78f2-...` |

> 数字校验：工具累计 478s > trace 总长 313s，因为 **3 个子 Agent 并行执行**，`task` 时间互相重叠。这不矛盾。

## 五、结论与优化建议

| 发现 | 证据 | 建议 |
|---|---|---|
| 88% 时间在模型生成 | 275.8s / 313.49s | 不换模型时，**砍输入**比换模型更有效：写作节点输入 80K tokens，可在综合阶段先做摘要 |
| 慢的不是首字节 | `start` 到 `first_token` 仅 1s，总 38.78s | 优化**输出长度**（分节写），不是调超时 |
| `tavily_search` 是唯一有实际耗时的工具 | 26 次 195s，平均 7.5s | 减少搜索轮数：把「最多搜 N 次」写进子 Agent 的 system prompt |
| 文件类工具零成本 | 27 次合计 0.05s | 不用优化 |

## 六、与教程参考值的对比

| 指标 | 教程（GLM） | 本项目（deepseek-v4.1-flash） |
|---|---|---|
| 总 Run 数 | 162 | 107（46 llm + 61 tool） |
| 总耗时 | 472.9s | 313.49s |
| 最慢 LLM 叶子 | 85.9s | 38.78s |
| 最慢真实工具 | tavily_search 25.1s | tavily_search 11.23s |
| 模型 Run 数 | 22 | 46（更多轮次，但每次更快） |

量级一致，说明模板行为和课程描述吻合。模型差异体现在「轮次多但单次快」vs「轮次少但单次慢」。

## 复现命令

```bash
export PATH="$HOME/.local/bin:$PATH"
cd ~/projects/research_deepagent
set -a; . ./.env; set +a

TID=01a1e46c-3547-7b10-bcca-4a9c7986215c
langsmith trace get $TID --project deepagents-course --include-metadata
langsmith run list --trace-ids $TID --project deepagents-course \
  --run-type llm --include-metadata --limit 100 --format json > llm.json
langsmith run list --trace-ids $TID --project deepagents-course \
  --run-type tool --include-metadata --limit 100 --format json > tool.json
```
