"""Generate a sample management PPT for the 松林漫步 launch case.

Demonstrates all six slide types: cover, agenda, divider, content
(bullets / cards / callout / kv / paragraph), data (bar / line / pie),
and closing. Run as:

    cd backend && python scripts/sample_management_ppt.py

Output lands at $BOXCC_BACKEND_DATA_DIR/exports/sample/松林漫步-发布提案.pptx
(or backend/data/exports/sample/ if env not set).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Make backend importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime_events import set_event_emitter, reset_event_emitter
from tools.management_ppt import create_management_ppt


def main() -> None:
    tokens = set_event_emitter(None, message_id="sample-msg", session_id="sample-sess", turn_id="sample")

    deck = {
        "meta": {
            "title": "松林漫步｜2026 秋冬新品发布提案",
            "subtitle": "把秋冬穿成一场安静的出走",
            "author": "品牌营销中心",
            "date": "2026.05.26",
            "brand": "松林漫步",
            "eyebrow": "Q4 NEW LAUNCH",
            "theme": "warm",
        },
        "slides": [
            {"type": "cover"},  # picks up meta
            {
                "type": "agenda",
                "title": "本次议程",
                "items": [
                    "系列定位与品牌故事",
                    "产品矩阵与核心卖点",
                    "上市营销节奏",
                    "投放与转化预期",
                    "下一步行动与决策项",
                ],
            },
            {
                "type": "divider",
                "title": "系列定位与品牌故事",
                "intro": "为什么是松林漫步、为什么是这个秋冬。",
            },
            {
                "type": "content",
                "title": "系列定位｜把秋冬穿成一场安静的出走",
                "eyebrow": "Series positioning",
                "lead": "面向 25–40 岁都市女性，以小众羊毛大衣为主角，秋冬场景化叠穿。",
                "blocks": [
                    {
                        "type": "cards",
                        "items": [
                            {"title": "情绪", "desc": "克制、自然、低饱和，安静耐看"},
                            {"title": "场景", "desc": "通勤、周末、聚会、短途旅行"},
                            {"title": "人群", "desc": "重视质感与日常搭配的都市女性"},
                            {"title": "传播主张", "desc": "「走进冬日的安静质感」"},
                        ],
                    },
                    {
                        "type": "callout",
                        "text": "不与同价位的「保暖大衣」竞争尺寸或克重，而是与「小众设计师品牌」竞争生活方式认同感。",
                    },
                ],
            },
            {
                "type": "divider",
                "title": "产品矩阵与核心卖点",
                "intro": "以 6 款大衣为主轴，价格带 ¥1,280–¥2,380，覆盖三种场景。",
            },
            {
                "type": "content",
                "title": "核心卖点｜可验证的质感",
                "eyebrow": "Selling points",
                "blocks": [
                    {
                        "type": "kv",
                        "items": [
                            {"label": "面料", "value": "羊毛 80% / 涤纶 20%，克重 520 g/m²"},
                            {"label": "色彩", "value": "燕麦、雾灰、松针绿、岩石棕"},
                            {"label": "版型", "value": "落肩剪裁，秋冬叠穿不臃肿"},
                            {"label": "执行标准", "value": "GB/T 2664-2017 · 安全 B 类"},
                        ],
                    },
                    {
                        "type": "callout",
                        "text": "所有保暖、起球、缩水承诺均以检测报告与吊牌为准；详情页 / 直播脚本不使用绝对化表达。",
                    },
                ],
            },
            {
                "type": "divider",
                "title": "上市营销节奏",
                "intro": "D-5 预热 → D-Day 发布 → D+14 复盘的短周期打法。",
            },
            {
                "type": "data",
                "title": "预算分配｜重心放在内容与直播",
                "eyebrow": "Budget",
                "takeaway": "首发期 ¥120 万投放：内容种草 50%、直播承接 28%、品牌大片 14%、CRM 8%。",
                "chart": {
                    "type": "pie",
                    "labels": ["KOL/KOC 内容", "直播带货", "品牌大片", "CRM/会员"],
                    "values": [60, 34, 17, 9],
                    "title": "首发期预算（万元）",
                },
            },
            {
                "type": "data",
                "title": "节奏预测｜首发后两周转化曲线",
                "eyebrow": "Forecast",
                "takeaway": "D-Day 至 D+3 出 50% GMV；D+7 后依靠达人长尾内容稳定 ROI。",
                "chart": {
                    "type": "line",
                    "categories": ["D-5", "D-3", "D-Day", "D+2", "D+5", "D+9", "D+14"],
                    "series": {
                        "曝光（万）": [12, 28, 86, 64, 38, 28, 22],
                        "GMV（万元）": [0, 0, 22, 18, 12, 9, 7],
                    },
                    "title": "曝光与 GMV 节奏",
                },
            },
            {
                "type": "data",
                "title": "渠道对比｜电商 + 自有 + 线下",
                "eyebrow": "Channels",
                "takeaway": "天猫 / 抖音 / 私域 / 门店各承担清晰角色，避免内卷价。",
                "chart": {
                    "type": "bar",
                    "categories": ["天猫", "抖音", "小红书", "私域", "线下"],
                    "series": {
                        "首批分货占比": [32, 26, 0, 14, 28],
                        "预计转化贡献": [38, 30, 8, 12, 12],
                    },
                    "title": "渠道分货 vs. 转化占比（%）",
                },
            },
            {
                "type": "content",
                "title": "合规边界｜上线前必审项",
                "eyebrow": "Compliance",
                "lead": "广告法 / 平台规则 / 达人合作 — 一次发布前的清单。",
                "blocks": [
                    {
                        "type": "bullets",
                        "items": [
                            "禁用绝对化与无法证明的表达：最高级、永久、零起球、全网最低、绝对",
                            "羊毛含量与克重必须以检测报告 / 吊牌为准，文案与详情页同源",
                            "KOL 合作内容显著标注「广告 / 商业合作」并保留素材授权文件",
                            "价格表述明确渠道与时间：限时活动价 / 会员日 / 直播间价",
                            "上线流程：营销初稿 → 内容校对 → 法务审查 → 平台规则复核",
                        ],
                    }
                ],
            },
            {
                "type": "closing",
                "title": "下一步与决策",
                "actions": [
                    {"owner": "品牌营销", "action": "完成主视觉与发布大片最终稿", "due": "06.05"},
                    {"owner": "内容社媒", "action": "锁定 12 位中腰部 KOL 排期", "due": "06.10"},
                    {"owner": "电商运营", "action": "天猫 / 抖音详情页与直播间脚本上线", "due": "06.18"},
                    {"owner": "法务合规", "action": "完成所有文案与达人 brief 合规复核", "due": "06.20"},
                ],
                "decisions": [
                    "首发期投放预算是否锁定 ¥120 万？",
                    "是否允许线下门店与电商同价同款？",
                    "重点合作的 3 位头部达人是否启动正式合同？",
                ],
            },
        ],
    }

    result = create_management_ppt.invoke({
        "filename": "松林漫步-发布提案-v2",
        "deck_json": json.dumps(deck, ensure_ascii=False),
    })
    print(result)
    reset_event_emitter(tokens)


if __name__ == "__main__":
    main()
