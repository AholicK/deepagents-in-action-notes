# pre02 · 为编码助手安装开发技能 + Trace 实操

> 课程原文：<https://datawhalechina.github.io/deepagents-in-action/chapters/pre02-agentseek-skills/>
> 前提：pre01 已完成，且 `.env` 里 `LANGSMITH_TRACING=true`

## 两类 Skill 的区别（先分清）

| 类型 | 使用者 | 安装方式 | 本文涉及 |
|---|---|---|---|
| **编码助手开发技能** | Codex / Claude Code / Cursor | `npx skills add ...` | ✅ |
| **DeepAgents 运行时 Skill** | 你构建的 Deep Agent | `create_deep_agent(skills=[...])` | ❌（第 7 章） |

两者都用 `SKILL.md`，但服务对象完全不同。

## 1. 查看可用技能

```bash
node --version && npm --version
cd ~/projects/research_deepagent
npx skills add ob-labs/agentseek --list
```

实测输出 4 个技能：

```
github-repo-cards
langchain-dev-guide     ← 本篇要装
langsmith-trace         ← 本篇要装
documentation-writer
```

## 2. 安装到当前项目

```bash
npx skills add ob-labs/agentseek \
  --skill langchain-dev-guide \
  --skill langsmith-trace \
  --agent cursor --yes
```

`--agent` 的可选值决定落地目录：

| 编码助手 | 项目级目录 | 全局目录 |
|---|---|---|
| Codex | `.agents/skills/` | `~/.agents/skills/` |
| Claude Code | `.claude/skills/` | `~/.claude/skills/` |
| Cursor | `.agents/skills/` | `~/.cursor/skills/` |

安装会带安全评估：

```
langchain-dev-guide  Safe / 0 alerts / Low Risk
langsmith-trace      Safe / 0 alerts / Med Risk
```

**没装编码助手 CLI 也能装**——文件照样落到 `.agents/skills/`，只是 `npx skills list` 会显示 `Agents: not linked`。

## 3. 验证安装

```bash
npx skills list
find .agents/skills -type f | sort
```

实测文件数：

```
langchain-dev-guide: 14 个（SKILL.md + 10 个 reference/*.md + template/chat_model.py）
langsmith-trace:      2 个（SKILL.md + reference/cli-commands.md）
```

## 4. 用 langchain-dev-guide 检查项目配置

教程要求的输入：

> 请使用 langchain-dev-guide 检查这个 deepagents/research 项目的模型配置。
> 请核对环境变量，并说明 Tool Call、reasoning_content 等能力的兼容性边界。

**没有编码助手时的替代做法**：直接读 `reference/deepagents.md` 和 `reference/model-integration.md` 自查。

### 实际配置

| 项 | 值 | 来源 |
|---|---|---|
| `AGENTSEEK_MODEL_PROVIDER` | `openai` | `.env` |
| `AGENTSEEK_MODEL` | `deepseek-v4.1-flash` | `.env` |
| 代码路径 | `init_chat_model(...)` → 底层 `ChatOpenAI` | `agent.py:133–152` |

### skill 记录的四条边界

**① `reasoning_content` 被静默丢弃**

> `_create_chat_result` 和 `_convert_chunk_to_generation_chunk` 不识别这个字段。

当前风险：**不触发**。实测该模型 `completion_tokens_details.reasoning_tokens: 0`、`content` 正常有文字。换成真 reasoning 模型（开思考模式）时前端会看不到思考过程。

**② 多轮对话 reasoning 上下文断**

> `_get_request_payload` 不处理 `additional_kwargs["reasoning_content"]`，上一轮推理链传不回模型。

同上，仅 reasoning 模型触发。

**③ 空 `tools: []` 触发 provider 400**

当前风险低：两个工具（`tavily_search`、`think_tool`）始终绑定。

**④ `invalid_tool_calls`（弱模型产出坏 JSON）**

已被 deepagents 内置的 `PatchToolCallsMiddleware` 覆盖——就是 Studio 图上第一个节点 `PatchToolCallsMiddleware.before_agent`。**不需要额外装 `ToolCallRepairMiddleware`**。

### 结论

当前配置（`deepseek-v4.1-flash` + `parallel_tool_calls=false` + 300s chunk timeout）安全。四条的现状：三条不触发，一条已被中间件覆盖。

---

## 5. langsmith-trace 实操

### 5.1 装 CLI 并认证

```bash
curl -fsSL https://cli.langsmith.com/install.sh | sh
command -v langsmith && langsmith --version    # 0.4.0

# 从 .env 加载凭证（不要用 --api-key 参数，会泄漏到 shell 历史）
cd ~/projects/research_deepagent
set -a; . ./.env; set +a

langsmith --format pretty project list
```

输出：

```
 NAME                 ID                                    RUNS  ERROR RATE  LAST ACTIVE
 deepagents-course    41f00083-df9f-43ab-90c8-0c24174ffb77   1    100.0%      2026-11-16 12:54
```

> 100% error 是隧道断掉那次失败的 run，不影响后续。

### 5.2 找 trace

```bash
langsmith trace list --project deepagents-course --name research \
  --include-metadata --limit 5
```

本项目的 trace 名称是 `LangGraph`（不是 `research`），所以用：

```bash
langsmith trace list --project deepagents-course --limit 5
# trace_id: 01a1e46c-3547-7b10-bcca-4a9c7986215c

langsmith trace get 01a1e46c-3547-7b10-bcca-4a9c7986215c \
  --project deepagents-course --include-metadata
```

输出是完整层级树（见 [trace-analysis.md](../trace/trace-analysis.md)）。

### 5.3 按类型分析瓶颈

```bash
TID=01a1e46c-3547-7b10-bcca-4a9c7986215c

# 所有 LLM 调用
langsmith run list --trace-ids $TID --project deepagents-course \
  --run-type llm --include-metadata --limit 100 --format json > llm.json

# 所有工具调用
langsmith run list --trace-ids $TID --project deepagents-course \
  --run-type tool --include-metadata --limit 100 --format json > tool.json
```

用 Python 聚合排序（**一定要排除 `task`**）：

```python
import json
llm = json.load(open("llm.json"))
tool = json.load(open("tool.json"))
dur = lambda r: r.get("duration_ms") or 0

print("LLM:", len(llm), "个, 总", sum(dur(r) for r in llm)/1000, "s")
for r in sorted(llm, key=dur, reverse=True)[:5]:
    print(f"  {dur(r)/1000:.2f}s", r.get("token_usage", {}).get("total_tokens"), r["run_id"])

real = [r for r in tool if r.get("name") != "task"]     # ← 关键：排除子 Agent 包装
for r in sorted(real, key=dur, reverse=True)[:5]:
    print(f"  {dur(r)/1000:.2f}s", r.get("name"), r["run_id"])
```

结果见 [trace-analysis.md](../trace/trace-analysis.md)。

### 5.4 检查分析结果

合格的分析必须包含：

| 检查项 | 完成标准 | 本项目 |
|---|---|---|
| Trace 选择 | 最近一次已完成的 research trace | ✅ 313.49s |
| 层级区分 | 根流程 / 子 Agent / 模型 / 工具 | ✅ |
| 模型瓶颈 | 最慢的 `run_type=llm` 叶子 | ✅ 38.78s / 80,090 tokens |
| 工具瓶颈 | 最慢的真实工具（排除 `task`） | ✅ tavily_search 11.23s |
| 证据 | run_id、耗时、状态、IO 检查 | ✅ |
| 建议 | 与证据对应 | ✅ |

## 6. 更新技能

```bash
npx skills update -p        # 项目级
npx skills update -g        # 全局级（如果装了）
npx skills list
```

## 7. 可选：全局安装

```bash
npx skills add ob-labs/agentseek \
  --skill langchain-dev-guide --skill langsmith-trace --global
```

## 移除

```bash
npx skills remove langchain-dev-guide langsmith-trace --yes
```
