# 协作开发指南

每位 agent 开始工作前按顺序阅读 `AGENTS.md`、`CONTEXT.md`、`MEMORY.md`。这三份文件用于替代对完整聊天历史的依赖：本文件说明**如何工作**，`CONTEXT.md` 说明**系统现在是什么**，`MEMORY.md` 记录**为何做过关键选择**。

## 接手流程

1. 先阅读三份协作文档，不要凭猜测改变产品边界或发布方式。
2. 查看 `git status --short`、最近提交和正在使用的分支；默认在隔离工作区修改，避免污染主工作区。
3. 对用户请求先区分：仅解释/诊断时不写代码；明确要求变更时才实现、测试、提交。
4. 完成后把仍有效的架构决定或运行问题更新到 `MEMORY.md`；不要把逐次对话、临时行情或提交日志塞进记忆文件。

## 工作边界

- 这是个人研究用的 QQQ 定投与仓位辅助仪表盘，不是交易执行系统，也不构成投资建议。
- 纳斯达克综合指数 `^IXIC` K 线只作市场走势展示，绝不能接入 QQQ 的加减仓决策。
- 不保存或提交券商、持仓、现金、密钥、Cookie、`.env` 或本地快照。

## 项目结构

- `app/`：FastAPI、行情提供方、指标、规则引擎与调度器。
- `static/`：无构建步骤的 HTML/CSS/JavaScript 仪表盘。
- `tests/`：pytest 测试；前端目前使用静态契约测试。
- `.github/workflows/publish-dashboard.yml`：GitHub Pages 构建与部署。

## 开发约定

1. 修改逻辑前先补或修改相关测试，并先观察失败，再实现最小改动。
2. 不改变 `app/services/decision.py` 的规则阈值、仓位范围或定投倍率，除非用户明确要求。
3. 保持暗色终端风格、涨绿 `#3DDC97`、跌红 `#F0656B`；同时验证手机端布局。
4. 数据源失败必须优雅降级：显示状态或上次快照，绝不伪造实时数据。
5. 提交前运行 `git diff --check` 和 `./.venv/Scripts/python.exe -m pytest -q`。
6. 前端新增或调整文案时，优先展示当前值、阈值和数据状态；不要只写“未触发”。

## 变更定位

- 修改信号或仓位：先检查 `app/services/decision.py`、规则配置与 `tests/test_decision.py`；这是高影响变更，必须得到用户明确授权。
- 修改行情/缓存：检查 `app/scheduler.py`、`app/providers/`、`app/services/dashboard.py` 与快照测试。
- 修改页面：检查 `static/index.html`、`static/assets/app.js`、`static/assets/style.css`；验证桌面和手机断点。
- 修改发布：检查 `.github/workflows/publish-dashboard.yml`；确认 `main` push、手动运行和定时刷新都未被意外移除。

## 常用命令

```powershell
.\.venv\Scripts\python.exe -m scripts.refresh_dashboard
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m pytest -q
```

## 发布

- 仅向 `main` 推送已验证的改动。
- 推送到 `main` 会触发 GitHub Pages 发布；工作流也会在工作日每 15 分钟刷新一次数据。
- Pages 静态资源可能被客户端缓存；核验更新时优先做强制刷新或使用带版本参数的 URL。

## 三份协作文档的维护边界

- `AGENTS.md`：工作规则、验证命令、目录职责。仅在协作流程变化时更新。
- `CONTEXT.md`：当前架构、数据流、规则接口与部署事实。系统结构变化时更新。
- `MEMORY.md`：经用户确认的长期偏好、风险边界、已复现的数据源问题。不要记录临时行情、个人信息或冗长过程。