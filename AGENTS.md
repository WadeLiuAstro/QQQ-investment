# 协作开发指南

每位 agent 开始工作前先阅读本文件、`CONTEXT.md` 与 `MEMORY.md`；三者共同构成当前项目的交接资料。

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
