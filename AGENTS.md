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

## 协作执行架构

### 角色与模型绑定

| 角色 | 模型 | 职责 |
|---|---|---|
| 主线程 | Qwen3.8 | 需求分析、架构设计、任务拆分、风险判断、代码审查、最终验收、合并与清理 |
| 子代理 | DeepSeek V4-flash | 边界明确、可验证、可回滚的具体 TDD 实现任务 |

涉及产品边界、规则阈值、发布方式的决策必须由主线程拍板，不下放。

项目已在 `.qoder/agents/` 定义两个定制子代理：`tdd-implementer`（任务卡驱动的 TDD 实现）与 `task-fixer`（验收不通过后的最小修正）；派发时主线程在提示词中指明使用哪个子代理。模型绑定取决于运行环境的可选模型，子代理定义文件本身不指定模型。

模型绑定目的：子代理在独立 worktree 中执行，每个子代理实例拥有完全隔离的文件系统视图，便于 DeepSeek V4-flash 执行层的进程隔离与任务调度；主 worktree 始终由主线程（Qwen3.8）独占，不受子代理执行影响。

### 子代理隔离方式（独立 worktree + 独立分支）

每个子代理任务必须在独立的 git worktree 和独立分支中执行，不再共用主 worktree：

- 基础分支由主线程在派发时指定（通常为开发分支 `qqq-dashboard`）。
- 主线程负责创建隔离环境：`git worktree add .worktrees/task-<任务名> -b task/<任务名> <基础 commit>`。
- 子代理只在自己的 worktree 内工作、测试与 commit；不得触碰主 worktree或其他子代理的 worktree。

### 任务派发规范

每个任务派发时必须包含任务卡：

1. **目标**：一句话描述交付物。
2. **基础 commit**：分支起点哈希（回滚基准）。
3. **独立 worktree 路径**：如 `.worktrees/task-sentiment-chart/`。
4. **分支名**：如 `task/sentiment-chart`。
5. **文件所有权**：本任务允许修改的文件清单，不得越界。
6. **验收标准**：可执行的测试命令或可观察的行为断言。
7. **约束**：不得自行扩大范围；未经主线程审核不得创建或合并 PR/分支；不得修改任务范围外的文件。

子代理执行流程（TDD 保留）：先写失败测试 → 最小实现 → 测试通过 → commit（含 conventional commits 前缀）。

完成后报告：分支名、commit 哈希、修改文件列表、测试结果、残余风险。

### 主线程验收流程

主线程收到子代理完成报告后，**不得仅凭文字报告判定完成**，必须进入子代理的 worktree 执行以下核验：

1. 检查真实 `git status --short`、分支指向与完整 `git diff <基础 commit>..HEAD`，确认无越界文件修改。
2. 在子代理 worktree 内重新运行 `pytest`（至少覆盖涉及模块），确认测试通过。
3. 如涉及前端变更，做浏览器端到端核验。
4. 发现问题时，将具体修正要求发回子代理（或派发修正任务给新实例）；验收不通过时可直接丢弃该 worktree 与分支回滚，不影响主工作区。
5. 审核通过后才允许合并回基础分支（合并由主线程执行，子代理无权自行合并）。

### 并行/串行规则

- **可并行**：任务之间无依赖，且文件所有权不重叠（各自独立 worktree 天然隔离文件系统）。
- **必须串行**：任务之间存在依赖关系，或会修改相同文件（如 `app/scheduler.py`、`static/assets/app.js`、`static/assets/style.css`）。
- 当前栈验收并合并完成后，再启动下一个依赖栈。

### 合并后清理

子代理分支合并后，主线程必须删除对应的 worktree 与分支，避免累积：

```powershell
git worktree remove .worktrees/task-<任务名>
git branch -d task/<任务名>
```

### 最终回归验证

所有任务栈完成后：

1. 执行全量 `pytest` + `git diff --check`。
2. 生成真实快照并做浏览器端到端核验（桌面 + 手机断点）。
3. 汇总实际改动、测试证据与残余风险。
4. 确认全部验收条件满足后，同步三份文档（roadmap / CONTEXT.md / MEMORY.md）并提交。

## Git 版本管理规范

1. 项目必须使用 Git 进行版本管理，所有功能变更须通过 `git commit` 记录；不得绕过版本控制直接修改线上文件。
2. 提交信息遵循 conventional commits 风格：`feat:`（新功能）、`fix:`（修复）、`docs:`（文档）、`chore:`（杂项）前缀。
3. 每个 S 迭代或独立功能完成后必须 `push` 到远端对应分支：开发分支 `qqq-dashboard`，验证后的改动合入主分支 `main`（push 到 main 会触发 GitHub Pages 发布）。
4. 不得将数据快照文件（`static/data/*.json`、`data/*.sqlite`）或 IDE 缓存（`.qoder/` 缓存内容、`__pycache__/`、`.venv/`）提交到版本库；这些路径由 `.gitignore` 排除（例外：`.qoder/agents/` 子代理定义属协作资产，纳入版本控制），新增生成物或缓存目录时须同步补入。

## 任务完成后的文档同步（强制）

每次完成一个开发任务（如一个 P0 迭代）并提交后，必须同步以下三份文档，缺一不可：

1. `docs/product-roadmap.md`：更新对应迭代的完成状态（✅）、交付记录（新增/修改的文件、测试用例数、提交哈希）与更新日期；推荐实施顺序中划掉已完成项。
2. `CONTEXT.md`：更新数据流、界面约定与文件地图等技术上下文（如 payload 新增字段、新增服务模块）。
3. `MEMORY.md`：记录经确认的决策变更、用户偏好与已复现问题；只写长期事实，不写过程流水。

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