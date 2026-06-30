"""玩家实体"""

from __future__ import annotations
import logging
from typing import Optional, TYPE_CHECKING

from .enums import Faction
from .container import Hand, Deck, Graveyard
from .card import CardInstance

log = logging.getLogger("gwent.player")

if TYPE_CHECKING:
    from .board import Board


class Player:
    """玩家实体"""

    def __init__(self, name: str, faction: Faction, is_ai: bool = False):
        self.name = name
        self.faction = faction
        self.is_ai = is_ai

        self.hand = Hand(f"{name}_hand")
        self.deck = Deck(f"{name}_deck")
        self.grave = Graveyard(f"{name}_grave")

        self.leader: Optional[CardInstance] = None
        self.leader_available: bool = True

        self.passed: bool = False
        self.round_wins: int = 0
        self._total_score: int = 0

        self._opponent: Optional['Player'] = None
        self._board: Optional['Board'] = None

    @property
    def opponent(self) -> Optional['Player']:
        return self._opponent

    @opponent.setter
    def opponent(self, other: 'Player'):
        self._opponent = other

    @property
    def board(self) -> Optional['Board']:
        return self._board

    @board.setter
    def board(self, board_instance: 'Board'):
        self._board = board_instance

    @property
    def total_score(self) -> int:
        if self._board is not None:
            return self._board.calculate_player_score(self)
        return self._total_score

    def update_total(self, delta: int) -> None:
        self._total_score += delta

    def reset_round(self) -> None:
        self.passed = False
        self._total_score = 0
        log.info(f"  🔄 {self.name} round reset (wins={self.round_wins})")
