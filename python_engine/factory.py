"""卡牌工厂函数"""

from __future__ import annotations
import json
import logging
from typing import List

from .enums import AbilityType, Faction, RowType
from .card import CardDefinition

log = logging.getLogger("gwent.factory")


def create_card_from_dict(data: dict) -> CardDefinition:
    """从字典创建卡牌定义（兼容JS数据格式）"""
    abilities_raw = data.get("ability", "").split()
    abilities = []
    for ab in abilities_raw:
        try:
            abilities.append(AbilityType(ab))
        except ValueError:
            pass

    strength_str = data.get("strength", "")
    base_strength = int(strength_str) if strength_str and str(strength_str).strip() else 0

    id_val = data.get("id", "")
    card_id = int(id_val) if id_val and str(id_val).strip() else 0

    row_str = data.get("row", "")
    try:
        row_type = RowType(row_str) if row_str else RowType.SPECIAL
    except ValueError:
        row_type = RowType.SPECIAL

    return CardDefinition(
        id=card_id,
        name=data["name"],
        faction=Faction(data["deck"]),
        row=row_type,
        base_strength=base_strength,
        abilities=tuple(abilities),
        max_count=int(data.get("count", 1)),
        filename=data.get("filename", ""),
        muster_name=data.get("muster", ""),
    )


def load_cards_from_json(json_str: str) -> List[CardDefinition]:
    """从JSON字符串加载卡牌库"""
    data_list = json.loads(json_str)
    return [create_card_from_dict(d) for d in data_list]


def load_cards_from_file(filepath: str) -> List[CardDefinition]:
    """从JSON文件加载卡牌库"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    cards = load_cards_from_json(content)
    log.info(f"📂 Loaded {len(cards)} card definitions from {filepath}")
    return cards
