# 消息面展示卡片（样本 C：预期事件 + 头条混排）实施计划

> 主线程设计文档。执行遵循 AGENTS.md 协作执行架构（独立 worktree + 任务卡派发 + 主线程验收）。
> 基础分支：`qqq-dashboard`。样式样本：Canvas `news-card-style-samples`，用户选定样本 C。

## 需求快照（grilling 已钉死）

- **定位**：独立消息面卡片，纯展示、永不耦合五档决策/仓位/倍率/闸门；未来可与归因（涨/跌）联动另议。
- **数据源（混合）**：现有宏观事件日历（FOMC/CPI/非农）打底 + CNBC RSS 头条增强；新闻源失败降级为纯日历视图。
- **语言**：英文标题原样 + 中文来源名（CNBC 宏观/CNBC 头条）+ 时间 + 原文链接。
- **判定**：只列头条，不做利多/利空判定。
- **节奏**：随日频全量刷新（一天一次），不加盘中任务。
- **窗口**：最近 3 天、最多 12 条头条；预期事件取最近 3 个。

## 数据源验证结论（2026-08-06 实测）

| 源 | URL | 结果 |
|---|---|---|
| CNBC 宏观（Economy） | `https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258` | ✅ 200、标准 RSS、数小时内更新 |
| CNBC 头条（US Top News） | `https://www.cnbc.com/id/100003114/device/rss/rss.html` | ✅ 同上 |
| Yahoo Finance RSS | — | ❌ 404 已死，不采用 |

## 契约冻结（payload 顶层 `news`）

```
news = {
  "available": bool,                     # 卡片整体可用（事件或头条至少其一有内容）
  "news_source_available": bool,         # RSS 源是否成功
  "upcoming": [                          # 最近 3 个未来事件，升序
    {"kind","title","event_at","days_until"}
  ],
  "headlines": [                         # 最近 3 天内、最多 12 条、时间降序
    {"title","url","source","published_at"}
  ]
}
```

- `source` 取值：`CNBC 宏观` / `CNBC 头条`（中文来源名）。
- `days_until` 为向上取整天数；前端 ≤7 天用琥珀色"临近 · N 天"，否则绿色"N 天后"。
- 旧快照无 `news` 字段时前端隐藏整个 section（Pydantic 默认 None 兼容）。

## 降级矩阵

| 场景 | 行为 |
|---|---|
| RSS 抓取/解析失败 | `news_source_available=false`，头条区显示"新闻源暂不可用，仅展示排期事件" |
| 事件日历失败 | upcoming 为空，头条正常展示 |
| 两者都失败 | `available=false`，卡片显示"消息面暂不可用" |
| 3 天内无头条 | 头条区显示"近三日暂无收录头条" |

## 任务栈（文件所有权互斥分析）

### Task A：`task/news-rss-provider`（串行，第一栈）
- 文件：`app/providers/news_rss.py`（新建）、`tests/test_news_rss.py`（新建）
- 交付：`NewsItem` dataclass（title/url/published_at/source）；`fetch_rss_headlines(client) -> tuple[list[NewsItem], SourceStatus]`（抓两个 CNBC 源，httpx + 浏览器请求头，stdlib xml.etree 解析，无新依赖）；纯解析函数 `parse_rss_items(xml_text, source) -> list[NewsItem]` 可单测
- 验收：正常 XML、畸形 XML、空 channel、HTTP 错误、418 均不抛异常；测试绿

### Task B：`task/news-board-service`（依赖 A）
- 文件：`app/services/newsboard.py`（新建）、`app/models.py`（新增 NewsHeadline/NewsUpcoming/NewsBoard + DashboardPayload.news）、`tests/test_newsboard.py`（新建）
- 交付：`build_newsboard(events, items, now, news_available) -> NewsBoard`（3 天窗口过滤、12 条上限、降序、upcoming 取未来最近 3 个含 days_until、降级矩阵）
- 验收：窗口/上限/排序/降级逐用例覆盖；旧快照 JSON（无 news）model_validate 通过

### Task C：`task/news-scheduler-wiring`（依赖 B）
- 文件：`app/scheduler.py`、`app/services/dashboard.py`、`tests/test_news_payload.py`（新建）
- 交付：日频路径抓取 RSS（try 隔离，失败只降级新闻子区）→ `build_newsboard` → payload 顶层 `news`；守护路径（run_intraday_guard）不抓新闻
- 验收：payload 含 news；RSS 失败时 decision 等正式字段逐字节不变

### Task D：`task/news-frontend`（与 C 并行，契约已冻结）
- 文件：`static/index.html`、`static/assets/app.js`、`static/assets/style.css`、`tests/test_news_static.py`（新建）
- 交付：`#news-section`（monitoring-section 之后）+ `renderNewsCard`（样本 C 布局：3 张预期事件卡 + 头条列表 + 降级文案 + 脚注"随日频快照更新 · 覆盖最近 3 天 · 最多 12 条 · 仅陈述事实，不构成任何判断依据"）；链接 `target="_blank" rel="noopener"`
- 验收：静态契约测试锁定文案/字段名/位置顺序；全量 pytest 绿

## 最终回归（主线程）

1. 全量 pytest + `git diff --check`
2. 真实快照刷新（日频路径）+ 浏览器核验（桌面/手机断点、降级文案、链接可点）
3. 三文档同步 + 按功能分组提交
