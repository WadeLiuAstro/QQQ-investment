# S3 刷新架构重构实施计划（体系的"节奏"）

> 主线程设计文档。执行遵循 AGENTS.md 协作执行架构（独立 worktree + 独立分支 + 主线程验收）。
> 基础分支：`qqq-dashboard`，基础 commit：`589c20d`。

## 目标与边界

- 调度拆分为**日频全量刷新**（美东收盘后一次，产出正式信号）与**盘中轻量守护**（15 分钟，仅检测熔断级事件）。
- 盘中守护不重算正式 payload（不触碰 decision、indicators、backtest、monitoring），只追加 `kind=circuit_breaker` 提醒与 `intraday_watch` 观测字段。
- `dashboard.json` 语义标注为"日频正式快照"（`snapshot_kind` + 生成时间）；盘中仅提醒条更新。
- GitHub Pages 工作流同步为双模式。
- **不修改**：五档状态、仓位区间、定投倍率、规则阈值、监控佐证层边界。

## 关键设计决策（主线程拍板）

1. 熔断阈值（常量写入 `app/services/intraday_guard.py`，测试锁定）：
   - QQQ 单日跌幅 ≤ -3%（live 报价 vs `Quote.previous_close`）
   - VIX 单日涨幅 ≥ +20% 或 VIX 绝对值 ≥ 35
2. 提醒去重：`key = f"circuit_breaker:{YYYY-MM-DD}:{qqq_drop|vix_spike}"`，同一交易日同一类型只提醒一次。
3. 守护只在常规交易时段（`is_regular_session_open`）执行，时段外直接返回。
4. 本地调度（APScheduler）：日频 cron `mon-fri 16:35 America/New_York` 跑 `refresh_once`；interval 15 分钟跑 `run_intraday_guard`（自守门）。
5. 手动 `/api/refresh` 保持全量刷新语义（用户主动触发的开发工具，不属自动节奏）。
6. payload 新增字段均带默认值，旧快照兼容：`snapshot_kind: str = "daily"`、`intraday_watch: IntradayWatch | None = None`。

## 任务栈（文件所有权互斥分析后确定）

### Task A：`task/s3-guard-service`（串行，第一栈）
- 文件：`app/services/intraday_guard.py`（新建）、`app/models.py`（新增字段）、`tests/test_intraday_guard.py`（新建）
- 交付：`detect_circuit_events(qqq_quote, vix_quote) -> list[GuardFinding]`、`build_circuit_alerts(findings, day) -> list[Alert]`、`IntradayWatch` 模型、payload 两个新字段
- 验收：新测试覆盖阈值边界（-3.0 触发 / -2.9 不触发；+20% / 35 绝对线）、去重 key 格式、None 报价降级；全量 pytest 绿

### Task B：`task/s3-scheduler-dual`（依赖 A）
- 文件：`app/scheduler.py`、`tests/test_scheduler.py`、`tests/test_scheduler_runtime.py`
- 交付：`run_intraday_guard(repository, export_path, fetch_quote=...)`（时段守门 + 只更新 alerts/intraday_watch + 落库导出）；`create_refresh_scheduler` 双 job
- 验收：守护触发时 decision 与正式字段逐字节不变（对比 fixture）；时段外 no-op；双 job 注册测试

### Task D：`task/s3-frontend`（与 B 并行，文件不重叠，契约已冻结）
- 文件：`static/assets/app.js`、`static/assets/style.css`、`static/index.html`（如需）、`tests/test_snapshot_semantics_static.py`（新建）
- 交付：`alertKindNames` 增 `circuit_breaker:'熔断预警'`；数据状态区展示"日频正式快照 · 生成于 {generated_at}"与盘中守护状态（`intraday_watch` 存在时）；静态契约测试锁定文案与字段名
- 验收：静态测试绿；全量 pytest 绿

### Task C：`task/s3-script-workflow`（依赖 B）
- 文件：`scripts/refresh_dashboard.py`、`.github/workflows/publish-dashboard.yml`、`tests/test_publish_workflow.py`
- 交付：脚本 `--mode auto|daily|guard`（auto = 盘中跑守护、盘后跑全量）；工作流保持 `*/15 * * * 1-5` cron，命令改为 `--mode auto`
- 验收：工作流静态测试更新通过；脚本三种模式的行为测试

## 最终回归（主线程）

1. 全量 pytest + `git diff --check`
2. 真实快照刷新（日频路径）+ 浏览器核验（提醒条、快照标注、桌面/手机）
3. 三文档同步（roadmap / CONTEXT.md / MEMORY.md）+ 按功能分组提交
