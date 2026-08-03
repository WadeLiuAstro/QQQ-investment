# Dashboard Explanation Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让板块佐证单行可读，并将中性状态下的规则结果解释为具体数值与阈值。

**Architecture:** 在 `static/assets/app.js` 增加仅展示用途的解释格式化函数；在 `style.css` 调整板块卡片网格。后端决策引擎保持不变。

**Tech Stack:** 原生 HTML、CSS、JavaScript；pytest 静态契约测试。

## Global Constraints

- 不修改 QQQ 信号阈值、仓位范围或定投倍率。
- 桌面端板块使用两列，移动端使用单列。
- 恐贪数据缺失必须明确标记为未纳入判断。

---

### Task 1: 前端解释与板块排版

**Files:**
- Modify: `static/assets/app.js`
- Modify: `static/assets/style.css`
- Test: `tests/test_signal_explanation_static.py`

- [x] **Step 1: Write the failing test**

```python
def test_dashboard_explains_threshold_results_and_uses_inline_sector_cards() -> None:
    script = Path("static/assets/app.js").read_text(encoding="utf-8")
    styles = Path("static/assets/style.css").read_text(encoding="utf-8")
    assert "formatSignalBreakdown" in script
    assert "VIX（恐慌指数）" in script
    assert "sector-name" in script
    assert ".sector{display:flex" in styles
```

- [x] **Step 2: Run test to verify it fails**

Run: `.\\.venv\\Scripts\\python.exe -m pytest tests/test_signal_explanation_static.py -q`
Expected: FAIL because the formatter and inline sector styles do not exist.

- [x] **Step 3: Write minimal implementation**

```javascript
function formatSignalBreakdown(indicators, decision) { /* render current values and fixed rule thresholds */ }
```

Render two-column desktop sector cards and one-column mobile cards using `sector-name` and `sector-price` spans.

- [x] **Step 4: Run tests to verify they pass**

Run: `.\\.venv\\Scripts\\python.exe -m pytest -q`
Expected: PASS.

- [x] **Step 5: Commit**

```powershell
git add static/assets/app.js static/assets/style.css tests/test_signal_explanation_static.py
git commit -m "feat: clarify dashboard signal explanations"
```