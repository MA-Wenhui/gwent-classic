"""游戏状态管理"""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import List, Optional, Callable

from .player import Player

log = logging.getLogger("gwent.state")


@dataclass
class RoundResult:
    round_number: int
    winner: Optional[Player]
    player1_score: int
    player2_score: int


class GameState:
    """游戏全局状态"""

    def __init__(self, player1: Player, player2: Player):
        self.player1 = player1
        self.player2 = player2
        player1.opponent = player2
        player2.opponent = player1

        self.round_count: int = 0
        self.max_rounds: int = 3
        self.current_player: Optional[Player] = None
        self.first_player: Optional[Player] = None
        self.round_history: List[RoundResult] = []

        self.random_respawn: bool = False
        self.double_spy_power: bool = False

        self.game_start_hooks: List[Callable] = []
        self.round_start_hooks: List[Callable] = []
        self.round_end_hooks: List[Callable] = []

    @property
    def is_playing(self) -> bool:
        return self.round_count < self.max_rounds

    def get_winner(self) -> Optional[Player]:
        p1_wins = self.player1.round_wins
        p2_wins = self.player2.round_wins
        if p1_wins >= 2:
            log.info(f"  🏆 Game winner: {self.player1.name} ({p1_wins}-{p2_wins})")
            return self.player1
        if p2_wins >= 2:
            log.info(f"  🏆 Game winner: {self.player2.name} ({p2_wins}-{p1_wins})")
            return self.player2
        log.info(f"  🤝 No winner yet ({p1_wins}-{p2_wins})")
        return None
