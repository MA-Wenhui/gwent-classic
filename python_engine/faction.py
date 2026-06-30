"""阵营被动能力"""

from __future__ import annotations
import logging
import random
from typing import Dict, Optional, Callable, Any, TYPE_CHECKING

from .enums import Faction, RowType

log = logging.getLogger("gwent.faction")

if TYPE_CHECKING:
    from .player import Player
    from .game_state import GameState


class FactionAbility:
    """阵营被动能力（对应 JS factions.js）"""

    def __init__(
        self,
        faction: Faction,
        description: str,
        game_start_hook: Optional[Callable[['Player', 'GameState'], Any]] = None,
        round_start_hook: Optional[Callable[['Player', 'GameState'], Any]] = None,
        round_end_hook: Optional[Callable[['Player', 'GameState'], Any]] = None,
    ):
        self.faction = faction
        self.description = description
        self.game_start_hook = game_start_hook
        self.round_start_hook = round_start_hook
        self.round_end_hook = round_end_hook

    def register(self, player: 'Player', game_state: 'GameState') -> None:
        """将阵营能力注册到游戏事件钩子中"""
        if self.game_start_hook is not None:
            game_state.game_start_hooks.append(
                lambda p=player, gs=game_state: self.game_start_hook(p, gs)
            )
        if self.round_start_hook is not None:
            game_state.round_start_hooks.append(
                lambda p=player, gs=game_state: self.round_start_hook(p, gs)
            )
        if self.round_end_hook is not None:
            game_state.round_end_hooks.append(
                lambda p=player, gs=game_state: self.round_end_hook(p, gs)
            )


def create_faction_abilities() -> Dict[Faction, FactionAbility]:
    """创建所有阵营被动能力"""
    abilities: Dict[Faction, FactionAbility] = {}

    # Northern Realms: 赢得一轮后抽一张牌
    def realms_round_start(player: 'Player', game_state: 'GameState') -> None:
        if game_state.round_count > 1:
            prev_result = game_state.round_history[-1]
            if prev_result.winner is player:
                player.deck.draw(player.hand, 1)

    abilities[Faction.NORTHERN_REALMS] = FactionAbility(
        faction=Faction.NORTHERN_REALMS,
        description="Draw a card from your deck whenever you win a round.",
        round_start_hook=realms_round_start,
    )

    # Nilfgaard: 平局时获胜（在回合结算逻辑中处理）
    abilities[Faction.NILFGAARD] = FactionAbility(
        faction=Faction.NILFGAARD,
        description="Wins any round that ends in a draw.",
    )

    # Monsters: 每轮结束后保留一个随机单位
    def monsters_round_end(player: 'Player', game_state: 'GameState') -> None:
        if player.board is None:
            return
        rows = player.board.get_player_rows(player)
        all_units = []
        for row in rows:
            all_units.extend(row.get_units())
        if not all_units:
            return
        kept_card = all_units[random.randint(0, len(all_units) - 1)]
        kept_card.no_remove = True

        game_state.round_start_hooks.append(lambda _kc=kept_card: setattr(_kc, 'no_remove', False))

    abilities[Faction.MONSTERS] = FactionAbility(
        faction=Faction.MONSTERS,
        description="Keeps a random Unit Card out after each round.",
        round_end_hook=monsters_round_end,
    )

    # Scoia'tael: 决定谁先手
    def scoiatael_game_start(player: 'Player', game_state: 'GameState') -> None:
        if game_state.first_player is None:
            game_state.first_player = player

    abilities[Faction.SCOIATAEL] = FactionAbility(
        faction=Faction.SCOIATAEL,
        description="Decides who takes first turn.",
        game_start_hook=scoiatael_game_start,
    )

    # Skellige: 第三轮开始时从墓地复活2个随机单位
    def skellige_round_start(player: 'Player', game_state: 'GameState') -> None:
        if game_state.round_count != 3:
            return
        if player.board is None:
            return
        units = player.grave.find_cards_random(lambda c: c.is_unit, 2)
        for card in units:
            player.grave.remove_card(card)
            target_row_type = card.definition.row
            if target_row_type == RowType.AGILE:
                target_row_type = RowType.CLOSE
            if target_row_type in (RowType.CLOSE, RowType.RANGED, RowType.SIEGE):
                target_row = player.board.get_row(player, target_row_type)
                card.holder = player
                card.current_row = target_row_type
                target_row.add_card(card)
                target_row.update_state(card, True)
                target_row.update_scores()

    abilities[Faction.SKELLIGE] = FactionAbility(
        faction=Faction.SKELLIGE,
        description="2 random cards from the graveyard are placed on the battlefield at the start of the third round.",
        round_start_hook=skellige_round_start,
    )

    return abilities
