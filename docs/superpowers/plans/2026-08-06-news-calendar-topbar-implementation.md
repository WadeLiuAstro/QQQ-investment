# 消息面日历视图 + 顶部头条摘要栏 实施计划

> 主线程设计文档（grilling 定稿）。执行遵循 AGENTS.md 协作执行架构。
> 基础分支：`qqq-dashboard`。

## 需求快照（用户拍板）

### A. 消息面卡内嵌月历
- 消息面卡片内的"3 张预期事件卡"升级为**当月网格日历**：事件窗口放宽到 35 天
- 空日显示空白格，事件日用圆点标注，点按/悬停显示事件名与日期
- 跨月处理：固定显示当前月；若下月有事件，月末标注"+N 下月事件"
- 手机端：7 列压缩网格（小格 + 圆点），点按看详情
- BLS 被封期间日历会稀疏（只有 FOMC），属预期，接受

### B. 顶部头条摘要栏（不做滚动跑马灯）
- 位置：信号带下方；内容：最新最多 3 条头条
- 动效：3 条叠位淡入淡出轮换，8 秒/条；悬停/点按暂停；尊重 `prefers-reduced-motion`（减弱动效时直接静态显示第一条）
- 常驻标注"消息面 · 日频更新 {时间}"——明确不暗示实时
- 点击整栏跳转（平滑滚动）到 `#news-section`
- 头条为空时整栏隐藏

## 主线程补充决策

1. 监控区"临近高影响事件"（`monitoring.groups.macro_defensive.details.events`）仍按 **7 天**过滤，保持"临近"语义；35 天窗口只服务消息面日历。
2. `newsboard.UPCOMING_LIMIT` 从 3 提升到 10（35 天窗口事件数可能超过 3；前端日历全量使用）。
3. alerts（3 天窗口）与归因（3 天窗口）独立过滤，已核实不受影响。

## 任务栈（文件依赖决定全部串行：A → B → C）

### Task A：`task/news-window-backend`（后端窗口）
- 文件：`app/scheduler.py`（事件窗口 7→35 天；传给 monitoring 的 events 预过滤 7 天）、`app/services/newsboard.py`（UPCOMING_LIMIT 3→10）、`tests/test_newsboard.py` + 相关调度/payload 测试更新
- 验收：35 天窗口事件进入 `news.upcoming`（最多 10 个）；monitoring details.events 不含 >7 天事件；既有降级语义不变

### Task B：`task/news-calendar-frontend`（月历视图）
- 文件：`static/assets/app.js`、`static/assets/style.css`、`static/index.html`（如需）、`tests/test_news_static.py`（更新/新增）
- 交付：`renderNewsCalendar`（当月网格、事件点、点按显示事件、"+N 下月事件"标注、手机压缩网格）替换 `#news-upcoming` 的事件卡渲染；保留既有降级文案路径
- 验收：静态契约测试锁定结构与文案；决策渲染不受影响

### Task C：`task/news-topbar`（顶部头条摘要栏）
- 文件：同 B 组文件（与 B 串行原因）
- 交付：`#news-ticker-bar`（信号带下方）+ 淡入淡出轮换（8s）+ 悬停/点按暂停 + `prefers-reduced-motion` 静态降级 + "消息面 · 日频更新 {时间}"标注 + 点击滚动到 `#news-section`；头条为空隐藏
- 验收：静态契约测试锁定文案/id/动效参数；不引入任何第三方动效库

## 最终回归（主线程）

1. 全量 pytest + `git diff --check`
2. 真实快照刷新 + 浏览器核验（桌面月历/轮换动效、手机压缩网格、减弱动效降级、点击跳转）
3. 三文档同步 + 提交
