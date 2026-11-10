"""超短交易计划执行复盘提示词与流式生成。"""
from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是一位专注 A 股超短线交易的执行教练。你的任务不是预测行情或推荐股票，而是根据用户提供的交易计划与实际执行记录，找出“计划质量—执行纪律—结果”之间的偏差，并给出下一阶段可执行的改进规则。

## 数据边界

- 只能使用用户消息中给出的记录和统计，不得补充任何外部行情、新闻或个股判断。
- 必须引用具体数字和具体记录（日期/代码/模式）说明结论。
- 已结束样本少于 8 笔时，必须明确写出“样本不足，以下结论置信度低”，不得把偶然结果当成稳定规律。
- 不预测明日涨跌，不给出具体标的的买卖建议。改进建议只能针对流程、规则和记录方式。
- 只输出结论，不输出推导过程或“我先看……”之类的元话语。

## 输出结构（Markdown）

### 1. 结论摘要
用 3 条以内的要点概括：执行上最值得保留的优点、最影响结果的问题、当前样本的可信度。

### 2. 计划与执行偏差
- 入场上限、追高、低于计划价、仓位超计划、止损未执行分别出现了多少次，举 1-2 条代表性记录。
- 说明这些偏差与收益/R 倍数的关系；没有执行数据的计划单独说明计划质量问题。

### 3. 模式与情绪画像
- 按模式（首板、接力、低吸、半路、反包等）和市场情绪分组，指出哪些组合有正期望、哪些组合样本太少。
- 区分“模式本身无效”和“执行走了样”，不要只看胜率。

### 4. 主要漏洞
按影响从大到小列出最多 3 个漏洞。每条必须包含：现象、证据、导致的后果、可验证的修正动作。

### 5. 下一阶段规则
给出 3-5 条可以写进交易纪律的规则，必须带明确阈值或触发条件，例如“入场价超过计划上限 0.3% 即放弃”“单笔风险不超过计划仓位的 1.2 倍”。不要写“保持谨慎”这类空话。

### 6. 复盘检查清单
用勾选清单分别列出：盘前、盘中、盘后各 2-4 项。只保留能直接执行的动作。

末尾固定一行：
> 以上分析仅基于你记录的交易计划与执行数据，用于流程复盘，不构成投资建议。"""

_SETUP_LABEL = {
    "first_board": "首板打板",
    "relay": "连板接力",
    "dip": "低吸",
    "halfway": "半路",
    "reversal": "反包",
    "leader_first_yin": "龙头首阴",
    "other": "其他",
}
_MOOD_LABEL = {
    "ice": "冰点",
    "repair": "修复",
    "ferment": "发酵",
    "climax": "高潮",
    "ebb": "退潮",
    "skip": "不参与",
}
_STATUS_LABEL = {
    "planned": "待执行",
    "entered": "持仓中",
    "exited": "已结束",
    "missed": "未执行",
    "cancelled": "已取消",
}


def _fmt(value: Any, digits: int = 1, suffix: str = "", signed: bool = False) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    prefix = "+" if signed and number > 0 else ""
    return f"{prefix}{number:.{digits}f}{suffix}"


def _short(value: Any, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit] + ("…" if len(text) > limit else "")


def build_user_prompt(rows: list[dict], stats: dict, focus: str) -> str:
    lines = [
        "## 区间统计",
        f"- 计划 {stats.get('total', 0)} 条；已执行 {stats.get('executed', 0)} 条；"
        f"已结束 {stats.get('closed', 0)} 条；未执行 {stats.get('missed', 0)} 条；"
        f"取消 {stats.get('cancelled', 0)} 条",
        f"- 执行率 {_fmt(stats.get('execution_rate'), 1, '%')}；"
        f"胜率 {_fmt(stats.get('win_rate'), 1, '%')}；"
        f"平均单笔 {_fmt(stats.get('avg_pnl_pct'), 2, '%', signed=True)}；"
        f"平均 R {_fmt(stats.get('avg_r'), 2, signed=True)}",
        f"- 平均盈利 {_fmt(stats.get('avg_win_pct'), 2, '%', signed=True)}；"
        f"平均亏损 {_fmt(stats.get('avg_loss_pct'), 2, '%', signed=True)}；"
        f"盈亏比 {_fmt(stats.get('profit_factor'), 2)}",
        f"- 纪律分 {_fmt(stats.get('discipline_score'), 0)}；"
        f"追高 {stats.get('chase_count', 0)} 次；"
        f"跌破止损未离场 {stats.get('stop_breach_count', 0)} 次",
    ]
    flags = stats.get("flag_counts") or []
    if flags:
        lines.append("- 问题标签: " + "、".join(f"{item['label']}×{item['count']}" for item in flags))

    for title, key in (("按模式", "by_setup"), ("按情绪", "by_mood")):
        groups = stats.get(key) or []
        if groups:
            lines.append(f"\n### {title}")
            for group in groups:
                lines.append(
                    f"- {_SETUP_LABEL.get(group['key'], _MOOD_LABEL.get(group['key'], group['key']))}: "
                    f"执行 {group['count']} 条，结束 {group['closed']} 条，"
                    f"胜率 {_fmt(group.get('win_rate'), 1, '%')}，"
                    f"平均 {_fmt(group.get('avg_pnl_pct'), 2, '%', signed=True)}，"
                    f"平均 R {_fmt(group.get('avg_r'), 2, signed=True)}"
                )

    lines.append("\n## 逐条计划")
    for index, row in enumerate(rows, 1):
        metrics = row.get("metrics") or {}
        flags = "、".join(flag["label"] for flag in row.get("flags") or []) or "无"
        lines.append(
            f"{index}. {row.get('plan_date')} {row.get('symbol')} {row.get('name') or ''} | "
            f"{_SETUP_LABEL.get(str(row.get('setup')), row.get('setup'))} | "
            f"情绪 {_MOOD_LABEL.get(str(row.get('market_mood')), row.get('market_mood'))} | "
            f"状态 {_STATUS_LABEL.get(str(row.get('status')), row.get('status'))} | "
            f"信心 {row.get('confidence')}/5 | 计划持有 {row.get('planned_hold')} | "
            f"计划 {_fmt(row.get('planned_entry_low'), 2)}-{_fmt(row.get('planned_entry_high'), 2)} "
            f"止损 {_fmt(row.get('stop_loss'), 2)} 目标 {_fmt(row.get('target_price'), 2)} | "
            f"实际 {_fmt(row.get('actual_entry_price'), 2)}→{_fmt(row.get('actual_exit_price'), 2)} | "
            f"买入时间 {row.get('entry_at') or '—'} 卖出时间 {row.get('exit_at') or '—'} | "
            f"收益 {_fmt(metrics.get('pnl_pct'), 2, '%', signed=True)} | "
            f"R {_fmt(metrics.get('r_multiple'), 2, signed=True)} | "
            f"入场偏离 {_fmt(metrics.get('entry_deviation_pct'), 2, '%', signed=True)} | "
            f"纪律 {_fmt(metrics.get('discipline_score'), 0)} | 标签 {flags} | "
            f"计划逻辑: {_short(row.get('thesis'), 120)} | "
            f"失效条件: {_short(row.get('invalidation'), 80)} | "
            f"执行复盘: {_short(row.get('review'), 160)}"
        )

    if focus.strip():
        lines.append("\n## 本次额外关注点\n" + focus.strip())
    lines.append("\n请基于以上数据输出执行复盘。")
    return "\n".join(lines)


def build_meta(stats: dict) -> dict:
    return {
        "type": "meta",
        "plan_count": stats.get("total", 0),
        "closed_count": stats.get("closed", 0),
        "execution_rate": stats.get("execution_rate"),
        "win_rate": stats.get("win_rate"),
        "avg_pnl_pct": stats.get("avg_pnl_pct"),
        "avg_r": stats.get("avg_r"),
        "discipline_score": stats.get("discipline_score"),
    }


async def analyze_plans_stream(rows: list[dict], stats: dict, focus: str) -> AsyncIterator[str]:
    """NDJSON 事件流：meta / delta / error / done。"""
    yield json.dumps(build_meta(stats), ensure_ascii=False)

    from app.services.ai_provider import stream_ai_text

    got_content = False
    try:
        async for delta in stream_ai_text(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(rows, stats, focus)},
            ],
            temperature=0.4,
            max_tokens=None,
            prefer_final_answer=True,
        ):
            if not delta:
                continue
            got_content = True
            yield json.dumps({"type": "delta", "content": delta}, ensure_ascii=False)
    except Exception as exc:
        logger.exception("trade plan AI review failed: %s", exc)
        yield json.dumps({"type": "error", "message": f"AI 复盘失败: {exc}"}, ensure_ascii=False)
        return

    if not got_content:
        yield json.dumps(
            {"type": "error", "message": "AI 未返回正文（输出可能被截断），请重试"},
            ensure_ascii=False,
        )
        return
    yield json.dumps({"type": "done"}, ensure_ascii=False)
