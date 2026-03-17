"""Bettor personas for World V2 Market simulation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BettorPersona:
    """A specific type of market participant that places bets."""
    
    persona_id: str
    display_name: str
    description: str
    budget_yuan: int


def build_bettor_personas(base_budget: int = 50) -> list[BettorPersona]:
    """Build the standard set of bettor personas for the market simulation."""
    return [
        BettorPersona(
            "bettor_conservative",
            "保守型彩民_老王",
            "极度厌恶风险。喜欢买保本玩法（如选4、选5），绝不碰选9选10。一旦上一期亏损，本期投入减半。",
            base_budget,
        ),
        BettorPersona(
            "bettor_coverage",
            "技术型覆盖_李姐",
            "喜欢算概率，热衷于胆拖和复式。相信大数定律，总是尽可能覆盖更多号码组合。",
            base_budget * 2,
        ),
        BettorPersona(
            "bettor_upside",
            "搏冷爆发型_阿强",
            "只看大奖。非选9、选10不买，经常买单式多倍或冲刺冷门号。不在乎几期没中，只求一次爆发。",
            base_budget,
        ),
        BettorPersona(
            "bettor_contrarian",
            "逆向操盘手_老赵",
            "专门跟热门共识反着买。如果排行榜第一名或共识帖推荐了某个号，他必定避开。喜欢找连冷号。",
            base_budget,
        ),
        BettorPersona(
            "bettor_follower",
            "无脑跟风者_小明",
            "没有主见。总是看排行榜谁准就抄谁的作业，或者全盘复制共识度最高的号码。",
            base_budget,
        ),
        BettorPersona(
            "bettor_ziwei_believer",
            "紫微信徒_青玄",
            "只看玄学预测。对数据派冷嘲热讽，严格按照紫微斗数排盘的卦象号码下单。",
            base_budget,
        ),
        BettorPersona(
            "bettor_syndicate",
            "合买团_龙哥",
            "预算极高。喜欢在市场里集资，主打选9选10大复式。会参考多方意见，有很强的风险管理和兜底方案。",
            base_budget * 10,
        ),
    ]
