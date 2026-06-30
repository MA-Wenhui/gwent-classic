"""
游戏主循环引擎
对应 JS gwent.js 中的 Game 类
"""

from __future__ import annotations
import logging
import random
from typing import List, Optional, TYPE_CHECKING

from .enums import Faction, RowType, AbilityType
from .card import CardDefinition, CardInstance
from .container import Hand, Deck, Graveyard
from .board import Board, BoardRow
from .player import Player
from .game_state import GameState, RoundResult

log = logging.getLogger("gwent.engine")
from .faction import create_faction_abilities
from .factory import load_cards_from_file, create_card_from_dict
from .abilities import (
    register_card_definitions,
    build_placed_callbacks,
    build_removed_callbacks,
    get_leader_ability,
)


class GameEngine:
    """游戏引擎：管理完整的游戏生命周期"""

    def __init__(self, cards_path: str = "python_engine/cards.json"):
        self.card_definitions: List[CardDefinition] = load_cards_from_file(cards_path)
        register_card_definitions(self.card_definitions)
        self.faction_abilities = create_faction_abilities()

        self.game_state: Optional[GameState] = None
        self.board: Optional[Board] = None

    def setup_game(
        self,
        player1_faction: Faction,
        player2_faction: Faction,
        player1_deck_ids: Optional[List[tuple]] = None,
        player2_deck_ids: Optional[List[tuple]] = None,
        player1_leader_id: Optional[int] = None,
        player2_leader_id: Optional[int] = None,
        player2_is_ai: bool = True,
    ) -> None:
        """初始化一局游戏"""
        player1 = Player("Player1", player1_faction, is_ai=False)
        player2 = Player("Player2", player2_faction, is_ai=player2_is_ai)

        self.game_state = GameState(player1, player2)
        self.board = Board(self.game_state)

        self._build_deck(player1, player1_faction, player1_deck_ids, player1_leader_id)
        self._build_deck(player2, player2_faction, player2_deck_ids, player2_leader_id)

        self._init_leader_abilities(player1)
        self._init_leader_abilities(player2)
        self._check_whiteflame()

        faction_ab = self.faction_abilities.get(player1_faction)
        if faction_ab:
            faction_ab.register(player1, self.game_state)
        faction_ab = self.faction_abilities.get(player2_faction)
        if faction_ab:
            faction_ab.register(player2, self.game_state)

    def _build_deck(
        self,
        player: Player,
        faction: Faction,
        deck_ids: Optional[List[tuple]],
        leader_id: Optional[int],
    ) -> None:
        """构建玩家牌堆和领袖"""
        if leader_id is not None:
            leader_def = self._get_definition_by_id(leader_id)
            if leader_def:
                player.leader = CardInstance(definition=leader_def, holder=player)

        if deck_ids is None:
            deck_ids = self._default_deck_for_faction(faction)

        for card_id, count in deck_ids:
            card_def = self._get_definition_by_id(card_id)
            if card_def is None:
                continue
            for _ in range(count):
                instance = CardInstance(definition=card_def, holder=player)
                instance.placed_callbacks = build_placed_callbacks(instance)
                instance.removed_callbacks = build_removed_callbacks(instance)
                player.deck.add_card(instance)

        player.deck.shuffle()

    def _get_definition_by_id(self, card_id: int) -> Optional[CardDefinition]:
        for d in self.card_definitions:
            if d.id == card_id:
                return d
        return None

    def _default_deck_for_faction(self, faction: Faction) -> List[tuple]:
        """返回阵营默认卡组（取该阵营所有单位卡各1张，上限30张）"""
        faction_cards = [
            d for d in self.card_definitions
            if d.faction == faction and d.is_unit
        ]
        neutral_cards = [
            d for d in self.card_definitions
            if d.faction == Faction.NEUTRAL and d.is_unit
        ]
        special_cards = [
            d for d in self.card_definitions
            if d.faction == Faction.SPECIAL
        ]
        weather_cards = [
            d for d in self.card_definitions
            if d.faction == Faction.WEATHER
        ]

        result = []
        for d in faction_cards[:20]:
            result.append((d.id, min(d.max_count, 1)))
        for d in neutral_cards[:4]:
            result.append((d.id, 1))
        for d in special_cards:
            result.append((d.id, min(d.max_count, 1)))
        for d in weather_cards[:2]:
            result.append((d.id, 1))
        return result[:30]

    def _init_leader_abilities(self, player: Player) -> None:
        """初始化领袖被动能力（注册 gameStart 钩子等）"""
        if player.leader is None or self.game_state is None:
            return
        for ability in player.leader.abilities:
            leader_ab = get_leader_ability(ability.value)
            if leader_ab is None:
                continue
            # emhyr_invader: 设置 randomRespawn
            if ability == AbilityType("emhyr_invader"):
                self.game_state.random_respawn = True
            # eredin_treacherous: 设置 doubleSpyPower
            elif ability == AbilityType("eredin_treacherous"):
                self.game_state.double_spy_power = True

    def _check_whiteflame(self) -> None:
        """Emhyr Whiteflame: 若任一方领袖是 whiteflame，双方禁用领袖能力
        对应 JS Game.initPlayers 中的检测逻辑"""
        if self.game_state is None:
            return
        p1_whiteflame = (
            self.game_state.player1.leader is not None
            and any(a.value == "emhyr_whiteflame" for a in self.game_state.player1.leader.abilities)
        )
        p2_whiteflame = (
            self.game_state.player2.leader is not None
            and any(a.value == "emhyr_whiteflame" for a in self.game_state.player2.leader.abilities)
        )
        if p1_whiteflame or p2_whiteflame:
            self.game_state.player1.leader_available = False
            self.game_state.player2.leader_available = False
            log.info("🚫 Emhyr Whiteflame detected: both leaders disabled")

    async def start_game(self) -> None:
        """开始游戏：执行开局钩子、抽牌、重抽"""
        if self.game_state is None or self.board is None:
            raise RuntimeError("Game not set up. Call setup_game() first.")

        for hook in self.game_state.game_start_hooks[:]:
            result = hook()
            if hasattr(result, '__await__'):
                result = await result
            if result is True:
                self.game_state.game_start_hooks.remove(hook)

        if self.game_state.first_player is None:
            self.game_state.first_player = random.choice(
                [self.game_state.player1, self.game_state.player2]
            )

        for _ in range(10):
            self.game_state.player1.deck.draw(self.game_state.player1.hand, 1)
            self.game_state.player2.deck.draw(self.game_state.player2.hand, 1)

        # 初始重抽：AI 自动重抽，人类玩家由上层 UI 处理
        await self._initial_redraw_ai(self.game_state.player2)

        log.info(f"🎮 Game started! First player: {self.game_state.first_player.name}")
        self.game_state.current_player = self.game_state.first_player

    async def _initial_redraw_ai(self, player: Player) -> None:
        """AI 初始重抽：交换最多2张低战力手牌（对应 JS ControllerAI.redraw）"""
        if not player.is_ai:
            return
        for _ in range(2):
            if not player.hand.cards:
                break
            weakest = min(player.hand.cards, key=lambda c: c.definition.base_strength)
            if weakest.definition.base_strength < 15:
                player.deck.swap(player.hand, weakest)

    async def play_card(
        self,
        player: Player,
        card: CardInstance,
        target_row: Optional[str] = None,
        decoy_target: Optional[CardInstance] = None,
    ) -> bool:
        """玩家打出一张卡牌

        Args:
            player: 出牌玩家
            card: 要打出的卡牌
            target_row: 目标行名称（close/ranged/siege），用于 horn/mardroeme/agile
            decoy_target: Decoy 交换的目标场上卡牌
        """
        if self.board is None or self.game_state is None:
            return False

        if card not in player.hand.cards:
            log.warning(f"  ⚠️  {player.name} tried to play {card.name} but it's not in hand")
            return False

        log.info(f"🃏 {player.name} plays {card.name} (str={card.current_strength}, abilities={[a.value for a in card.abilities]})")
        player.hand.remove_card(card)

        if card.definition.faction == Faction.WEATHER:
            await self.board.to_weather(card)
            return True

        if card.definition.faction == Faction.SPECIAL:
            if card.has_ability(AbilityType.DECOY):
                # Decoy: 将 decoy_target 从场上移回手牌，decoy 放到该行
                # 目标必须由调用方显式指定（JS AI 在 decoy() 中根据优先级选择目标后传入）
                if decoy_target is None:
                    log.info(f"  ⚠️  {player.name} played Decoy without target, returning to hand")
                    player.hand.add_card(card)
                    return False
                # 找到目标卡所在的行
                target_board_row = None
                for row_key, board_row in self.board.rows.items():
                    if decoy_target in board_row.cards:
                        target_board_row = board_row
                        break
                if target_board_row is None:
                    player.hand.add_card(card)
                    return False
                # 移除目标卡并放回手牌
                target_board_row.remove_card(decoy_target)
                target_board_row.update_state(decoy_target, False)
                player.hand.add_card(decoy_target)
                # 将 decoy 放到该行
                target_board_row.add_card(card)
                target_board_row.update_state(card, True)
                target_board_row.update_scores(self.game_state.double_spy_power)
                return True
            elif card.has_ability(AbilityType.HORN):
                row_type = self._resolve_special_row(target_row, player)
                if row_type:
                    target_board_row = self.board.get_row(player, row_type)
                    if target_board_row.special_card is not None:
                        player.hand.add_card(card)
                        return False
                    target_board_row.special_card = card
                    target_board_row.effects.horn += 1
                    target_board_row.update_scores(self.game_state.double_spy_power)
                    return True
                player.hand.add_card(card)
                return False
            elif card.has_ability(AbilityType.CLEAR_WEATHER):
                self.board.weather.clear_weather(self.board)
                return True
            elif card.has_ability(AbilityType.MARDROEME):
                row_type = self._resolve_special_row(target_row, player)
                if row_type:
                    target_board_row = self.board.get_row(player, row_type)
                    if target_board_row.special_card is not None:
                        player.hand.add_card(card)
                        return False
                    target_board_row.special_card = card
                    target_board_row.effects.mardroeme += 1
                    target_board_row.update_scores(self.game_state.double_spy_power)
                    return True
                player.hand.add_card(card)
                return False
            elif card.has_ability(AbilityType.SCORCH):
                # scorch 特殊卡不放入任何行，直接触发 placed 回调后进墓地
                # placed 回调已在 build_placed_callbacks 中注册
                for callback in card.placed_callbacks:
                    await callback(card, None)
                await self.board.to_grave(card)
                return True

        row_name = target_row or card.definition.row.value
        if row_name == "agile":
            row_name = "close"

        if card.has_ability(AbilityType.SPY):
            opponent = player.opponent
            if opponent:
                spy_row = row_name if row_name in ("close", "ranged", "siege") else "close"
                # spy 的 placed 回调已处理抽牌和 holder 切换，这里只负责放到对手行
                await self.board.add_card_to_row(card, spy_row, opponent)
                return True

        if row_name not in ("close", "ranged", "siege"):
            row_name = "close"

        # add_card_to_row 内部会触发 placed_callbacks，
        # muster/spy/medic/scorch_c/r/s 的逻辑已在回调中实现，无需在此重复调用
        await self.board.add_card_to_row(card, row_name, player)

        return True

    def _resolve_special_row(self, target_row: Optional[str], player: Player) -> Optional[RowType]:
        """解析特殊卡的目标行"""
        if target_row in ("close", "ranged", "siege"):
            return RowType(target_row)
        return None

    async def activate_leader(self, player: Player) -> bool:
        """激活领袖能力"""
        if self.board is None or player.leader is None or not player.leader_available:
            return False

        player.leader_available = False
        log.info(f"👑 {player.name} activates leader ability")

        for ability in player.leader.abilities:
            leader_ab = get_leader_ability(ability.value)
            if leader_ab:
                await leader_ab.activate(player.leader, self.board)
                return True

        return False

    async def pass_round(self, player: Player) -> None:
        """玩家跳过回合"""
        player.passed = True
        log.info(f"⏭️  {player.name} passed the round")

    async def end_round(self) -> RoundResult:
        """结束当前轮次，结算分数"""
        if self.game_state is None or self.board is None:
            raise RuntimeError("Game not running")

        p1_score = self.board.calculate_player_score(self.game_state.player1)
        p2_score = self.board.calculate_player_score(self.game_state.player2)

        winner: Optional[Player] = None
        if p1_score > p2_score:
            winner = self.game_state.player1
        elif p2_score > p1_score:
            winner = self.game_state.player2
        else:
            nilfgaard_p1 = self.game_state.player1.faction == Faction.NILFGAARD
            nilfgaard_p2 = self.game_state.player2.faction == Faction.NILFGAARD
            if nilfgaard_p1 and not nilfgaard_p2:
                winner = self.game_state.player1
            elif nilfgaard_p2 and not nilfgaard_p1:
                winner = self.game_state.player2

        if winner:
            winner.round_wins += 1

        result = RoundResult(
            round_number=self.game_state.round_count + 1,
            winner=winner,
            player1_score=p1_score,
            player2_score=p2_score,
        )
        winner_name = winner.name if winner else "Draw"
        log.info(f"🏁 Round {result.round_number} ended: P1={p1_score} P2={p2_score} → {winner_name}")
        self.game_state.round_history.append(result)
        self.game_state.round_count += 1

        for hook in self.game_state.round_end_hooks[:]:
            hook_result = hook()
            if hasattr(hook_result, '__await__'):
                hook_result = await hook_result
            if hook_result is True:
                self.game_state.round_end_hooks.remove(hook)

        await self.board.clear_round()

        self.game_state.player1.reset_round()
        self.game_state.player2.reset_round()

        for hook in self.game_state.round_start_hooks[:]:
            hook_result = hook()
            if hasattr(hook_result, '__await__'):
                hook_result = await hook_result
            if hook_result is True:
                self.game_state.round_start_hooks.remove(hook)

        if not self.game_state.is_playing:
            return result

        self.game_state.current_player = self.game_state.first_player

        return result

    def get_game_winner(self) -> Optional[Player]:
        """获取最终胜者"""
        if self.game_state is None:
            return None
        return self.game_state.get_winner()

    def get_status(self) -> dict:
        """获取当前游戏状态摘要"""
        if self.game_state is None or self.board is None:
            return {"status": "not_started"}

        return {
            "status": "playing" if self.game_state.is_playing else "finished",
            "round": self.game_state.round_count,
            "current_player": self.game_state.current_player.name if self.game_state.current_player else None,
            "player1": {
                "name": self.game_state.player1.name,
                "faction": self.game_state.player1.faction.value,
                "score": self.board.calculate_player_score(self.game_state.player1),
                "hand_size": len(self.game_state.player1.hand),
                "deck_size": len(self.game_state.player1.deck),
                "passed": self.game_state.player1.passed,
                "round_wins": self.game_state.player1.round_wins,
            },
            "player2": {
                "name": self.game_state.player2.name,
                "faction": self.game_state.player2.faction.value,
                "score": self.board.calculate_player_score(self.game_state.player2),
                "hand_size": len(self.game_state.player2.hand),
                "deck_size": len(self.game_state.player2.deck),
                "passed": self.game_state.player2.passed,
                "round_wins": self.game_state.player2.round_wins,
            },
            "winner": self.get_game_winner().name if self.get_game_winner() else None,
        }
