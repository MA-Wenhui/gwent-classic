"""Gwent Classic Python Engine"""

from .enums import Faction, RowType, AbilityType
from .card import CardDefinition, CardInstance
from .container import CardContainer, Hand, Deck, Graveyard
from .board import RowEffects, BoardRow, WeatherZone, Board, AbilityHandler
from .player import Player
from .game_state import GameState, RoundResult
from .faction import FactionAbility, create_faction_abilities
from .factory import create_card_from_dict, load_cards_from_json, load_cards_from_file
from .abilities import (
    register_card_definitions,
    build_placed_callbacks,
    build_removed_callbacks,
    get_leader_ability,
    execute_scorch,
    execute_muster,
    execute_spy,
    execute_medic,
    LEADER_ABILITIES,
)
from .game_engine import GameEngine

__all__ = [
    # Enums
    "Faction",
    "RowType",
    "AbilityType",
    # Card
    "CardDefinition",
    "CardInstance",
    # Container
    "CardContainer",
    "Hand",
    "Deck",
    "Graveyard",
    # Board
    "RowEffects",
    "BoardRow",
    "WeatherZone",
    "Board",
    "AbilityHandler",
    # Player
    "Player",
    # Game State
    "GameState",
    "RoundResult",
    # Faction
    "FactionAbility",
    "create_faction_abilities",
    # Factory
    "create_card_from_dict",
    "load_cards_from_json",
    "load_cards_from_file",
    # Abilities
    "register_card_definitions",
    "build_placed_callbacks",
    "build_removed_callbacks",
    "get_leader_ability",
    "execute_scorch",
    "execute_muster",
    "execute_spy",
    "execute_medic",
    "LEADER_ABILITIES",
    # Engine
    "GameEngine",
]
