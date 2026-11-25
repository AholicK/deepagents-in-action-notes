# DeepAgents in Action · 学习笔记

跟 [datawhalechina/deepagents-in-action](https://github.com/datawhalechina/deepagents-in-action) 课程 **pre01–pre02 + ch01–ch04** 的完整实录：环境搭建、命令解析、踩坑排查、Trace 瓶颈分析、三层架构源码核对、虚拟文件系统实测、任务规划与清单流转。

> English version: [README.en.md](README.en.md)
> **想一次读完 ch01–ch02？看单篇合订版：[agent-learning/notes/ch01-ch02-notes.md](agent-learning/notes/ch01-ch02-notes.md)**
> **ch03（虚拟文件系统 / 四种后端）单篇合订版：[agent-learning/notes/ch03-virtual-filesystem.md](agent-learning/notes/ch03-virtual-filesystem.md)**

## 环境

| 项 | 版本 |
|---|---|
| 宿主 | Windows 11 + WSL2 Ubuntu 26.04.1 LTS |
| Python（项目） | 3.13.18（uv 管理，系统 Python 3.14.4 不动） |
| Node / npm | 22.22.1 / **11.x**（apt 自带 9.2.0 有 bug，见踩坑 #3） |
| uv | 0.13.8 |
| AgentSeek | 0.1.6（生成项目）/ agentseek-api 0.2.3（运行时） |
| deepagents / langchain / langgraph | 0.7.8 / 1.4.3 / 1.2.14 |
| langchain-core / langchain-openai / langsmith | 1.6.7 / 1.6.7 / 0.14.4 |
| 模型 | OpenAI 兼容端点 + `deepseek-v4.1-flash` |
| 搜索 | Tavily（免费额度） |
| Trace | LangSmith `deepagents-course` 项目 |

**为什么用 WSL2 而不是原生 Windows**：`pylibseekdb`（seekdb 的内嵌客户端）只有 Linux wheel，Windows 上 `agentseek-api` 启动即报 `Embedded Client is not available`。

## 目录

```
├── README.md / README.en.md        中 / 英 说明
├── LICENSE
└── agent-learning/                 ← 全部学习内容都在这一个文件夹里
    ├── notes/                      中文笔记（pre01 → ch04）
    │   ├── pre01-agentseek-create.md    环境 → 建项目 → 装依赖 → 跑通
    │   ├── pre02-agentseek-skills.md    装编码助手技能 → Trace 实操
    │   ├── ch01-ch02-notes.md           ⭐ 单篇合订版（一次读完 ch01+ch02）
    │   ├── ch03-virtual-filesystem.md   ⭐ ch03 单篇合订版（文件系统 + 四种后端实测）
    │   ├── ch04-task-planning.md        ⭐ ch04 单篇合订版（write_todos + 清单流转 + 复盘）
    │   ├── ch01-agent-harness.md        三层架构 + 源码级核对（图节点/中间件顺序）
    │   ├── ch02-quickstart.md           第一个 Agent + 三要素→JSON Schema 实测
    │   └── troubleshooting.md           4 个真实故障与修法
    ├── experiments/               实验代码 + 原始结果 JSON（课程项目 experiments/ 的镜像副本）
    │   ├── ch03/
    │   │   ├── _scripted.py             ScriptedChatModel（按剧本调工具，零 token）
    │   │   ├── exp1_tools.py            7 个工具全跑 + files 变化轨迹
    │   │   ├── exp1b_edges.py           5 个 v0.7 边界（空结果/1000 上限/覆盖写/越界）
    │   │   ├── exp2_eviction.py         大结果卸载 + 读回 + 对照组
    │   │   ├── exp2b_trace.py           带 LangSmith tracing 的卸载实验
    │   │   ├── exp3_backends.py         四种后端对比（8 个断言）
    │   │   └── results/                 每次运行的 JSON 原始结果
    │   └── ch04/
    │       ├── common.py                模型/搜索/清单流转记录器
    │       ├── 01_probe_middleware.py   开关对比（Spy 模型，零成本）
    │       ├── 02_run_planning.py       5 步任务 + 清单时间线
    │       ├── 03_run_harness_report.py 官方示例 + Trace + 自动复盘
    │       ├── 03b_fix_trace.py         补查 trace + 实体级覆盖检查
    │       └── 0*.json                  每次运行的原始结果
    ├── notes-en/                   对应英文版
    ├── trace/
    │   └── trace-analysis.md            313s trace 的瓶颈分析（含数据）
    └── feedback/
        ├── 学习心得.md
        ├── learning-reflections.en.md
        ├── 课程内容反馈.md
        └── course-feedback.en.md
```

> `experiments/` 里的脚本「跑法」注释按课程项目 `research_deepagent/experiments/...` 写，本仓库是镜像副本，代码与结果 JSON 与课程项目一致。

## ch01–ch02 的 5 个硬结论（实测，非转述）

| 结论 | 证据 |
|---|---|
| `create_deep_agent()` 返回的是 **LangGraph 的 `CompiledStateGraph`** | `type(agent).__name__`；图里只有 4 个节点 |
| 默认绑定 **8 个工具**：7 个文件工具 + `task`，**没有 `execute`** | 用 Spy 模型截 `bind_tools` 的入参 |
| 默认 system prompt **只有你写的那句**（传 `"test"` → 收到 4 字符） | 用 Spy 模型截 `_generate` 的 messages |
| 加 `TodoListMiddleware` = **+1 工具 +1372 字符 system** | 开关前后对比，4 → 1376 |
| 工具三要素会被翻译成 JSON Schema，`Literal` → `enum`（硬锁） | `convert_to_openai_tool()` 输出 |

## ch03 的 6 个硬结论（实测，非转述）

| 结论 | 证据 |
|---|---|
| 卸载阈值 20,000 tokens = **精确 80,000 字符**（`NUM_CHARS_PER_TOKEN = 4`） | 源码常量 + 触发点实测 |
| 一次真实卸载：工具返回 **150,165 字符** → 模型实收 **2,389 字符**，压缩 **62.9 倍** | LangSmith trace 两个 run 对比 |
| 7 个内置工具**全在**卸载豁免名单，但 `read_file` 会用同一 80,000 字符预算**原地截断** | 对照组：读 2000 行只回 994 行 + `next_offset` |
| 落盘路径是 `/large_tool_results/<tool_call_id>`，**同 id 会覆盖** | `result["files"]` 键 + trace 原文 |
| `StateBackend` 同 thread 换 agent 能读，新 thread `File not found`；`StoreBackend + InMemoryStore` 跨 thread 能读、换实例读不到 | exp3 四种后端 8 个断言 |
| `grep(count)` 1500 个匹配只回 **1000** + 一句 Note，**数字不是真实总数** | exp1b 边界实测 |

## ch04 的 6 个硬结论（实测，非转述）

| 结论 | 证据 |
|---|---|
| 默认 8 工具、无 `write_todos`；加 `TodoListMiddleware` = **9 工具 + 1372 字符 system + `todos` 状态字段** | Spy 模型对比，`agent-learning/experiments/ch04/01_probe_result.json` |
| **工具存在 ≠ 会用**：3 步任务 `deepseek-v4.1-flash` 一次 `write_todos` 都没调（`todos=[]`）；5 步任务 + 硬规则才规划 | 02 两版运行对比 |
| 第一次写清单**不是「全 pending」**：第 1 项直接 `in_progress` | 任务① t=11.6 s、任务② t=8.0 s 两次都是 |
| 内置提示词要求「`write_todos` 串行调用」+「最终答案写在最后一次调用之后」→ 打勾是**批量**的、最后一项常停在 `in_progress` | 1372 字符原文 + 任务①时间线 |
| 清单闭合**不稳定**：任务① 末项停在 `in_progress`，任务② 5/5 全 `completed`（同模型同类任务） | 两次运行 `final_todos` |
| **82% 时间在 LLM**：7 次调用 83.1 s / 总 101.1 s；搜索 12 次不是瓶颈 | LangSmith trace `01a21180-…` |

## 关键成果

- 跑通 **3 次**完整深度研究，产出 3 份报告（1.1–1.3 万字，均带编号引用）
- LangSmith trace：**313.49s / 46 次 LLM 调用 / 61 次工具调用**
- 定位并修复模板 **2 个真实缺陷**（state 膨胀、run 状态不回收）
- 源码级核对 ch01–ch02 的 6 个可验证断言，**全部与本地 0.7.8 一致**（默认模型 / 默认提示词 / 默认工具数 / 中间件顺序 / 参数总数 / `execute` 为何缺席）
- ch04 跑通 **2 次**多步研究（77.3s / 101.1s），逐步记录清单时间线；把 `write_todos` 的 5 条说明书指令与 4 种实际现象一一对上

## 一句话速查：4 个坑

| 症状 | 根因 | 修法 |
|---|---|---|
| 页面彻底卡死 | `tavily_search` 无长度上限 → state 23 MB | `MAX_PAGE_CHARS = 8000` |
| 一直转圈 "Research in progress" | SSE 断开后 run 卡 `running` | `POST /threads/<tid>/runs/<rid>/cancel` |
| 又卡（这次放后台） | Chrome 冻结后台标签，SSE 被挂起 | 保持前台标签 |
| `npm ERR! ... 'edgesOut'` | npm 9.2.0 解 peer 依赖 bug | 升 npm 11 |

详细排查过程见 [agent-learning/notes/troubleshooting.md](agent-learning/notes/troubleshooting.md)。

## 判断「卡死」的三条命令

不要看页面猜，直接查 API：

```bash
# 1. 服务活着吗
curl -s http://127.0.0.1:2024/ok

# 2. 图跑完了吗（next 空 = 结束）
curl -s http://127.0.0.1:2024/threads/<tid>/state \
  | python3 -c "import sys,json; d=json.load(sys.stdin)['values']; print('msgs',len(d['messages']),'next',d.get('next'))"

# 3. run 状态收尾了吗
curl -s http://127.0.0.1:2024/threads/<tid>/runs \
  | python3 -c "import sys,json; [print(r['status'], r['run_id'][:20]) for r in json.load(sys.stdin)]"
```

判定表：

| `next` | run status | 结论 |
|---|---|---|
| 非空 | `running` | 真在跑，等 |
| `[]` | `running` | **跑完了但没回收** → cancel + 刷新 |
| `[]` | `success`/`error` | 前端问题 |

## 说明

- 本文档所有 API Key、服务器地址均以占位符表示，不含真实凭证。
- 课程原文：<https://datawhalechina.github.io/deepagents-in-action/>

## License

MIT
