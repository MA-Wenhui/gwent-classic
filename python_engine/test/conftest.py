"""测试公共 fixture 与工具函数"""

import sys
import os
import json
import asyncio
import random

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from python_engine.logger import setup_logger  # noqa: F401 - 初始化日志
from python_engine import (
    CardDefinition, CardInstance, Faction, RowType, AbilityType,
    Hand, Deck, Graveyard, CardContainer,
    BoardRow, RowEffects, WeatherZone, Player, GameState, Board,
    GameEngine,
)

# ============================================================================
# 常量
# ============================================================================

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
CARDS_PATH = os.path.join(PROJECT_ROOT, "python_engine", "cards.json")
DECKS_PATH = os.path.join(PROJECT_ROOT, "python_engine", "decks.json")

FACTION_MAP = {
    "realms": Faction.NORTHERN_REALMS,
    "nilfgaard": Faction.NILFGAARD,
    "monsters": Faction.MONSTERS,
    "scoiatael": Faction.SCOIATAEL,
    "skellige": Faction.SKELLIGE,
}


# ============================================================================
# 卡牌工厂
# ============================================================================

def make_card(name, strength, abilities=(), row=RowType.CLOSE, hero=False, muster_name=""):
    """快速创建测试用卡牌实例"""
    abs_tuple = (AbilityType.HERO,) + tuple(abilities) if hero else tuple(abilities)
    definition = CardDefinition(
        id=hash(name) % 10000,
        name=name,
        faction=Faction.NEUTRAL,
        row=row,
        base_strength=strength,
        abilities=abs_tuple,
        muster_name=muster_name,
    )
    return CardInstance(definition=definition)


def make_card_def(name, strength, abilities=(), row=RowType.CLOSE, hero=False, muster_name="", card_id=None):
    """快速创建测试用卡牌定义"""
    abs_tuple = (AbilityType.HERO,) + tuple(abilities) if hero else tuple(abilities)
    return CardDefinition(
        id=card_id if card_id is not None else hash(name) % 10000,
        name=name,
        faction=Faction.NEUTRAL,
        row=row,
        base_strength=strength,
        abilities=abs_tuple,
        muster_name=muster_name,
    )


# ============================================================================
# 游戏环境工厂
# ============================================================================

def create_game_state():
    """创建最小可用的 GameState + Board"""
    p1 = Player("P1", Faction.NORTHERN_REALMS)
    p2 = Player("P2", Faction.NILFGAARD)
    gs = GameState(p1, p2)
    board = Board(gs)
    return gs, board, p1, p2


def load_decks():
    """加载预设牌组"""
    with open(DECKS_PATH) as f:
        return json.load(f)


def deck_to_args(deck_data):
    """将 decks.json 条目转为 setup_game 参数"""
    faction = FACTION_MAP[deck_data["faction"]]
    leader_id = deck_data.get("leader")
    card_ids = [tuple(c) for c in deck_data["cards"]]
    return faction, leader_id, card_ids


def create_engine_with_decks(deck_index_1=0, deck_index_2=1):
    """使用预设牌组创建并初始化 GameEngine"""
    decks = load_decks()
    engine = GameEngine(CARDS_PATH)
    p1_f, p1_l, p1_c = deck_to_args(decks[deck_index_1])
    p2_f, p2_l, p2_c = deck_to_args(decks[deck_index_2])
    engine.setup_game(
        p1_f, p2_f,
        player1_deck_ids=p1_c, player1_leader_id=p1_l,
        player2_deck_ids=p2_c, player2_leader_id=p2_l,
    )
    return engine


async def simulate_random_game(engine, max_rounds=3, max_turns_per_round=50, play_probability=0.85):
    """模拟随机对局，返回每轮结果列表"""
    await engine.start_game()
    round_results = []

    for _ in range(max_rounds):
        if not engine.game_state.is_playing:
            break

        for _ in range(max_turns_per_round):
            player = engine.game_state.current_player
            opponent = player.opponent

            if player.passed and opponent.passed:
                break

            if player.passed:
                engine.game_state.current_player = opponent
                continue

            if player.hand.cards and random.random() < play_probability:
                card = random.choice(list(player.hand.cards))
                await engine.play_card(player, card)
            else:
                await engine.pass_round(player)

            engine.game_state.current_player = opponent

        # 确保双方都 pass
        if not engine.game_state.player1.passed:
            await engine.pass_round(engine.game_state.player1)
        if not engine.game_state.player2.passed:
            await engine.pass_round(engine.game_state.player2)

        result = await engine.end_round()
        round_results.append(result)

    return round_results
