# DeepAgents in Action · 学习笔记

跟 [datawhalechina/deepagents-in-action](https://github.com/datawhalechina/deepagents-in-action) 课程 **pre01–pre02 + ch01–ch02** 的完整实录：环境搭建、命令解析、踩坑排查、Trace 瓶颈分析、三层架构源码核对。

> English version: [README.en.md](README.en.md)
> **想一次读完 ch01–ch02？看单篇合订版：[notes/ch01-ch02-notes.md](notes/ch01-ch02-notes.md)**

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
├── notes/
│   ├── pre01-agentseek-create.md    环境 → 建项目 → 装依赖 → 跑通
│   ├── pre02-agentseek-skills.md    装编码助手技能 → Trace 实操
│   ├── ch01-ch02-notes.md           ⭐ 单篇合订版（一次读完 ch01+ch02）
│   ├── ch01-agent-harness.md        三层架构 + 源码级核对（图节点/中间件顺序）
│   ├── ch02-quickstart.md           第一个 Agent + 三要素→JSON Schema 实测
│   └── troubleshooting.md           4 个真实故障与修法
├── notes-en/                        对应英文版
├── trace/
│   └── trace-analysis.md            313s trace 的瓶颈分析（含数据）
├── feedback/
│   ├── 学习心得.md
│   ├── learning-reflections.en.md
│   ├── 课程内容反馈.md
│   └── course-feedback.en.md
└── assets/                          截图（可选）
```

## ch01–ch02 的 5 个硬结论（实测，非转述）

| 结论 | 证据 |
|---|---|
| `create_deep_agent()` 返回的是 **LangGraph 的 `CompiledStateGraph`** | `type(agent).__name__`；图里只有 4 个节点 |
| 默认绑定 **8 个工具**：7 个文件工具 + `task`，**没有 `execute`** | 用 Spy 模型截 `bind_tools` 的入参 |
| 默认 system prompt **只有你写的那句**（传 `"test"` → 收到 4 字符） | 用 Spy 模型截 `_generate` 的 messages |
| 加 `TodoListMiddleware` = **+1 工具 +1372 字符 system** | 开关前后对比，4 → 1376 |
| 工具三要素会被翻译成 JSON Schema，`Literal` → `enum`（硬锁） | `convert_to_openai_tool()` 输出 |

## 关键成果

- 跑通 **3 次**完整深度研究，产出 3 份报告（1.1–1.3 万字，均带编号引用）
- LangSmith trace：**313.49s / 46 次 LLM 调用 / 61 次工具调用**
- 定位并修复模板 **2 个真实缺陷**（state 膨胀、run 状态不回收）
- 源码级核对 ch01–ch02 的 6 个可验证断言，**全部与本地 0.7.8 一致**（默认模型 / 默认提示词 / 默认工具数 / 中间件顺序 / 参数总数 / `execute` 为何缺席）

## 一句话速查：4 个坑

| 症状 | 根因 | 修法 |
|---|---|---|
| 页面彻底卡死 | `tavily_search` 无长度上限 → state 23 MB | `MAX_PAGE_CHARS = 8000` |
| 一直转圈 "Research in progress" | SSE 断开后 run 卡 `running` | `POST /threads/<tid>/runs/<rid>/cancel` |
| 又卡（这次放后台） | Chrome 冻结后台标签，SSE 被挂起 | 保持前台标签 |
| `npm ERR! ... 'edgesOut'` | npm 9.2.0 解 peer 依赖 bug | 升 npm 11 |

详细排查过程见 [notes/troubleshooting.md](notes/troubleshooting.md)。

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
