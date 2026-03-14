"""Domain vocabulary for Ziwei graphing and retrieval."""

from __future__ import annotations


MAJOR_STARS = (
    "紫微",
    "天机",
    "太阳",
    "武曲",
    "天同",
    "廉贞",
    "天府",
    "太阴",
    "贪狼",
    "巨门",
    "天相",
    "天梁",
    "七杀",
    "破军",
)

PALACE_TERMS = (
    "命宫",
    "兄弟宫",
    "夫妻宫",
    "子女宫",
    "财帛宫",
    "疾厄宫",
    "迁移宫",
    "交友宫",
    "官禄宫",
    "田宅宫",
    "福德宫",
    "父母宫",
)

META_TERMS = (
    "紫微斗数",
    "命盘",
    "流年",
    "流月",
    "流日",
    "流时",
    "四化",
    "宫位",
    "星曜",
)

STEMS = ("甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸")
BRANCHES = ("子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥")

DOMAIN_TERMS = MAJOR_STARS + PALACE_TERMS + META_TERMS + STEMS + BRANCHES


def extract_domain_terms(text: str) -> tuple[str, ...]:
    """Extract known domain terms in a stable order."""
    matches = []
    for term in DOMAIN_TERMS:
        if term in text:
            matches.append(term)
    return tuple(matches)
