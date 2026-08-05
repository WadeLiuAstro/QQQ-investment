"""盘中熔断守护服务：检测 QQQ 大跌与 VIX 恐慌信号，产出熔断预警。

纯函数模块，不读写任何外部状态；报价缺失时优雅降级（跳过对应检测）。
"""

from dataclasses import dataclass
from datetime import date

from app.models import Alert
from app.providers.yahoo import Quote

# 熔断阈值（测试锁定，勿改）
QQQ_DROP_THRESHOLD_PCT = -3.0   # QQQ 单日跌幅阈值（%）
VIX_SPIKE_CHANGE_PCT = 20.0     # VIX 单日涨幅阈值（%）
VIX_ABSOLUTE_THRESHOLD = 35.0   # VIX 绝对恐慌线

_TITLES = {
    "qqq_drop": "熔断预警：QQQ 单日大跌",
    "vix_spike": "熔断预警：VIX 恐慌飙升",
}


@dataclass(frozen=True)
class GuardFinding:
    """一次盘中守护检测命中的发现。

    kind: "qqq_drop" | "vix_spike"
    metric: 当前变化百分比（%）或 VIX 绝对值
    threshold: 命中的阈值
    detail: 中文描述，如 "QQQ 单日下跌 3.4%"
    """

    kind: str
    metric: float
    threshold: float
    detail: str


def detect_circuit_events(
    qqq_quote: Quote | None, vix_quote: Quote | None
) -> list[GuardFinding]:
    """基于盘中报价检测熔断信号；报价缺失或无效时跳过对应检测。"""
    findings: list[GuardFinding] = []

    qqq_change = _change_pct(qqq_quote)
    if qqq_change is not None and qqq_change <= QQQ_DROP_THRESHOLD_PCT:
        findings.append(
            GuardFinding(
                kind="qqq_drop",
                metric=qqq_change,
                threshold=QQQ_DROP_THRESHOLD_PCT,
                detail=f"QQQ 单日下跌 {abs(qqq_change):.1f}%",
            )
        )

    vix_finding = _detect_vix(vix_quote)
    if vix_finding is not None:
        findings.append(vix_finding)
    return findings


def build_circuit_alerts(findings: list[GuardFinding], day: date) -> list[Alert]:
    """将盘中发现转换为熔断预警，key 含日期与类型以便按日去重。"""
    alerts: list[Alert] = []
    for finding in findings:
        alerts.append(
            Alert(
                key=f"circuit_breaker:{day.isoformat()}:{finding.kind}",
                kind="circuit_breaker",
                title=_TITLES[finding.kind],
                detail=_alert_detail(finding),
            )
        )
    return alerts


def _change_pct(quote: Quote | None) -> float | None:
    """计算相对昨收的变化百分比；报价或昨收无效时返回 None。"""
    if quote is None or not quote.previous_close:
        return None
    return (quote.price - quote.previous_close) / quote.previous_close * 100


def _detect_vix(vix_quote: Quote | None) -> GuardFinding | None:
    """检测 VIX 恐慌信号：涨幅达标或绝对值达标（两条路径只产出一条）。"""
    change_pct = _change_pct(vix_quote)
    if change_pct is not None and change_pct >= VIX_SPIKE_CHANGE_PCT:
        return GuardFinding(
            kind="vix_spike",
            metric=change_pct,
            threshold=VIX_SPIKE_CHANGE_PCT,
            detail=f"VIX 单日上涨 {change_pct:.1f}%",
        )
    if (
        vix_quote is not None
        and vix_quote.previous_close
        and vix_quote.price >= VIX_ABSOLUTE_THRESHOLD
    ):
        return GuardFinding(
            kind="vix_spike",
            metric=vix_quote.price,
            threshold=VIX_ABSOLUTE_THRESHOLD,
            detail=f"VIX 达到 {vix_quote.price:.1f}",
        )
    return None


def _alert_detail(finding: GuardFinding) -> str:
    """预警正文 = 发现描述 + 阈值说明。"""
    if finding.kind == "qqq_drop":
        return f"{finding.detail}（阈值：单日跌幅 ≤ {QQQ_DROP_THRESHOLD_PCT:.1f}%）"
    if finding.threshold == VIX_SPIKE_CHANGE_PCT:
        return f"{finding.detail}（阈值：单日涨幅 ≥ {VIX_SPIKE_CHANGE_PCT:.1f}%）"
    return f"{finding.detail}（恐慌线：VIX ≥ {VIX_ABSOLUTE_THRESHOLD:.1f}）"
