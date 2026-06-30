"""战场行、天气系统与战场管理器"""

from __future__ import annotations
import logging
import random
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Callable, Any, TYPE_CHECKING

from .enums import AbilityType, RowType
from .card import CardInstance
from .container import CardContainer

log = logging.getLogger("gwent.board")

if TYPE_CHECKING:
    from .player import Player
    from .game_state import GameState


# ============================================================================
# Row Effects & Board Row
# ============================================================================

@dataclass
class RowEffects:
    """行的效果状态，对应 JS Row.effects"""
    weather: bool = False
    half_weather: bool = False
    horn: int = 0
    morale: int = 0
    mardroeme: int = 0
    bond: Dict[int, int] = field(default_factory=dict)


class BoardRow(CardContainer):
    """战场的一行"""

    def __init__(self, row_type: RowType, owner: Optional['Player'] = None):
        super().__init__(name=f"{owner.name}_{row_type.value}" if owner else row_type.value)
        self.row_type = row_type
        self.owner = owner
        self.effects = RowEffects()
        self.special_card: Optional[CardInstance] = None
        self.total_score: int = 0

    def update_state(self, card: CardInstance, activate: bool) -> None:
        """更新卡牌对行效果的影响（对应 JS Row.updateState）"""
        delta = 1 if activate else -1
        for ability in card.abilities:
            if ability in (AbilityType.MORALE, AbilityType.HORN, AbilityType.MARDROEME):
                attr_name = ability.value.replace(" ", "_")
                current = getattr(self.effects, attr_name, 0)
                setattr(self.effects, attr_name, current + delta)
            elif ability == AbilityType.BOND:
                # JS 中 bond 按卡牌名称分组（card.id() returns name）
                bond_key = card.name
                if bond_key not in self.effects.bond:
                    self.effects.bond[bond_key] = 0
                self.effects.bond[bond_key] += delta
            elif ability == AbilityType.VILDKAARL_MORALE:
                self.effects.morale += delta
            elif ability == AbilityType.VILDKAARL_BOND:
                bond_key = card.name
                if bond_key not in self.effects.bond:
                    self.effects.bond[bond_key] = 0
                self.effects.bond[bond_key] += delta

    def calculate_card_score(self, card: CardInstance, double_spy_power: bool = False) -> int:
        """计算单张卡牌在当前行效果下的实际战力（对应 JS Row.calcCardScore）"""
        if card.name == "Decoy":
            return 0

        total = card.definition.base_strength

        if card.is_hero:
            return total

        if self.effects.weather:
            weather_min = total // 2 if self.effects.half_weather else 1
            total = min(weather_min, total)

        if double_spy_power and card.has_ability(AbilityType.SPY):
            total *= 2

        # JS 中 bond 按卡牌名称分组
        bond_count = self.effects.bond.get(card.name, 0)
        if bond_count > 1:
            total *= bond_count

        morale_bonus = self.effects.morale
        if card.has_ability(AbilityType.MORALE):
            morale_bonus -= 1
        total += max(0, morale_bonus)

        horn_count = self.effects.horn
        if card.has_ability(AbilityType.HORN):
            horn_count -= 1
        if horn_count > 0:
            total *= 2

        return total

    def calculate_score(self, double_spy_power: bool = False) -> int:
        """计算该行的总战力"""
        return sum(
            self.calculate_card_score(card, double_spy_power)
            for card in self._cards
        )

    def update_scores(self, double_spy_power: bool = False) -> None:
        """更新所有卡牌的 current_strength 和行总分"""
        total = 0
        for card in self._cards:
            score = self.calculate_card_score(card, double_spy_power)
            card.set_power(score)
            total += score
        old_total = self.total_score
        self.total_score = total
        if old_total != total:
            log.debug(f"  📊 [{self.name}] score: {old_total} → {total}")

    def get_max_units(self) -> List[CardInstance]:
        """获取战力最高的单位卡列表"""
        units = [c for c in self._cards if c.is_unit]
        if not units:
            return []
        max_power = max(c.current_strength for c in units)
        return [c for c in units if c.current_strength == max_power]

    def get_virtual_copy(self, exclude_predicate: Optional[Callable] = None) -> 'BoardRow':
        """创建虚拟副本（用于AI模拟计算）"""
        virtual = BoardRow(self.row_type, self.owner)
        virtual.effects = RowEffects(
            weather=self.effects.weather,
            half_weather=self.effects.half_weather,
            horn=self.effects.horn,
            morale=self.effects.morale,
            mardroeme=self.effects.mardroeme,
            bond=dict(self.effects.bond),
        )
        for card in self._cards:
            if exclude_predicate is None or not exclude_predicate(card):
                cloned = card.clone()
                virtual.add_card(cloned)
                virtual.update_state(cloned, True)
        return virtual

    async def add_card_with_board(self, card: CardInstance, board: 'Board') -> None:
        """添加卡牌到行中，更新状态并触发 placed 回调"""
        if card.definition.is_special:
            self.special_card = card
        else:
            super().add_card(card)
            self.update_state(card, True)

        log.info(f"  🎴 Placed: {card.name} → {self.name} (abilities={[a.value for a in card.abilities]})")
        for callback in card.placed_callbacks:
            await callback(card, self)

        double_spy = board.game.double_spy_power if board else False
        self.update_scores(double_spy)

        # 打印放置卡牌后的完整 board 状态
        if board:
            log.debug(board.dump_state())

    def remove_card_with_callbacks(self, card: CardInstance) -> Optional[CardInstance]:
        """移除卡牌，更新状态并触发 removed 回调"""
        if card.definition.is_special:
            self.special_card = None
            removed = card
        else:
            removed = super().remove_card(card)
            if removed:
                removed.reset_power()
                self.update_state(removed, False)

        if removed:
            log.info(f"  ❌ Removed: {removed.name} from {self.name}")
            for callback in removed.removed_callbacks:
                callback(removed)

        # 移除卡牌后必须重新计算行分数，保持 total_score 与 current_strength 同步
        # 注意：此处无法获取 double_spy_power，使用默认值；
        # 后续 add_card_with_board / update_scores 会再次修正
        self.update_scores()

        # 打印移除卡牌后的完整 board 状态（需要找到所属 board）
        # BoardRow 没有直接引用 board，通过 owner.board 获取
        if self.owner and hasattr(self.owner, 'board') and self.owner.board:
            log.debug(self.owner.board.dump_state())

        return removed


# ============================================================================
# Weather System
# ============================================================================

class WeatherZone(CardContainer):
    """天气区域管理（对应 JS Weather 类）"""

    WEATHER_TYPES = ("rain", "fog", "frost", "storm")

    def __init__(self):
        super().__init__("weather")
        self.type_counts: Dict[str, int] = {t: 0 for t in self.WEATHER_TYPES}
        self._affected_rows: Dict[str, List[BoardRow]] = {}

    def register_rows(self, rows: List[BoardRow]) -> None:
        """注册受天气影响的行
        
        rows 顺序: [p1_close, p1_ranged, p1_siege, p2_close, p2_ranged, p2_siege]
        frost → close 行 (index 0, 3)
        fog   → ranged 行 (index 1, 4)
        rain  → siege 行 (index 2, 5)
        storm → ranged + siege 行 (index 1, 2, 4, 5)
        """
        for weather_type in self.WEATHER_TYPES:
            self._affected_rows[weather_type] = []

        # 按 row_type 分组
        close_rows = [r for r in rows if r.row_type == RowType.CLOSE]
        ranged_rows = [r for r in rows if r.row_type == RowType.RANGED]
        siege_rows = [r for r in rows if r.row_type == RowType.SIEGE]

        self._affected_rows["frost"] = close_rows
        self._affected_rows["fog"] = ranged_rows
        self._affected_rows["rain"] = siege_rows
        self._affected_rows["storm"] = ranged_rows + siege_rows

    def add_weather_card(self, card: CardInstance, board: 'Board') -> bool:
        """添加天气卡，返回是否为重复天气"""
        is_duplicate = any(c.name == card.name for c in self._cards)
        super().add_card(card)

        if card.name == "Clear Weather":
            self.clear_weather(board)
            return False

        double_spy = board.game.double_spy_power if board and board.game else False
        for ability in card.abilities:
            ability_value = ability.value
            if ability_value in self.type_counts:
                self.type_counts[ability_value] += 1
                if self.type_counts[ability_value] == 1:
                    for row in self._affected_rows.get(ability_value, []):
                        row.effects.weather = True
                        row.update_scores(double_spy)

        return is_duplicate

    def remove_weather_card(self, card: CardInstance, board: 'Board') -> None:
        """移除天气卡，更新行效果"""
        super().remove_card(card)
        double_spy = board.game.double_spy_power if board and board.game else False
        for ability in card.abilities:
            ability_value = ability.value
            if ability_value in self.type_counts:
                self.type_counts[ability_value] -= 1
                if self.type_counts[ability_value] == 0:
                    for row in self._affected_rows.get(ability_value, []):
                        row.effects.weather = False
                        row.update_scores(double_spy)

    def clear_weather(self, board: 'Board') -> None:
        """清除所有天气效果和卡牌"""
        for card in list(reversed(self._cards)):
            self.remove_weather_card(card, board)
        self._cards.clear()
        for weather_type in self.type_counts:
            self.type_counts[weather_type] = 0

    def reset(self) -> None:
        self._cards.clear()
        for weather_type in self.type_counts:
            self.type_counts[weather_type] = 0


# ============================================================================
# Board
# ============================================================================

class Board:
    """战场管理器"""

    def __init__(self, game_state: 'GameState'):
        self.game = game_state
        self.rows: Dict[tuple, BoardRow] = {}
        self.weather = WeatherZone()

        players = [game_state.player1, game_state.player2]
        row_types = [RowType.CLOSE, RowType.RANGED, RowType.SIEGE]

        for player in players:
            player.board = self
            for row_type in row_types:
                key = (id(player), row_type)
                self.rows[key] = BoardRow(row_type, player)

        all_rows = []
        for player in players:
            for row_type in row_types:
                all_rows.append(self.get_row(player, row_type))
        self.weather.register_rows(all_rows)

    def get_row(self, player: 'Player', row_type: RowType) -> BoardRow:
        return self.rows[(id(player), row_type)]

    def get_player_rows(self, player: 'Player') -> List[BoardRow]:
        return [
            self.get_row(player, RowType.CLOSE),
            self.get_row(player, RowType.RANGED),
            self.get_row(player, RowType.SIEGE),
        ]

    def calculate_player_score(self, player: 'Player') -> int:
        return sum(
            row.calculate_score(self.game.double_spy_power)
            for row in self.get_player_rows(player)
        )

    def resolve_row_target(self, card: CardInstance, row_name: str, player: Optional['Player'] = None) -> BoardRow:
        """根据行名称解析目标行（spy 卡放到对手行）"""
        target_player = player if player else card.holder
        is_spy = card.has_ability(AbilityType.SPY)
        actual_player = target_player.opponent if is_spy else target_player

        row_map = {
            "close": RowType.CLOSE,
            "ranged": RowType.RANGED,
            "siege": RowType.SIEGE,
        }

        if row_name in row_map:
            return self.get_row(actual_player, row_map[row_name])

        raise ValueError(f"Invalid row name '{row_name}' for card '{card.name}'")

    async def move_to(
        self,
        card: CardInstance,
        destination: str | BoardRow | CardContainer,
        source: Optional[CardContainer] = None,
    ) -> None:
        """通用卡牌移动方法（对应 JS Board.moveTo）"""
        if isinstance(destination, str):
            if destination == "grave":
                dest_container = card.holder.grave
            elif destination == "deck":
                dest_container = card.holder.deck
            elif destination == "hand":
                dest_container = card.holder.hand
            elif destination == "weather":
                dest_container = self.weather
            else:
                dest_container = self.resolve_row_target(card, destination)
        else:
            dest_container = destination

        if source is not None:
            if isinstance(source, BoardRow):
                source.remove_card_with_callbacks(card)
            else:
                source.remove_card(card)

        if isinstance(dest_container, BoardRow):
            await dest_container.add_card_with_board(card, self)
        elif isinstance(dest_container, WeatherZone):
            is_dup = dest_container.add_weather_card(card, self)
            if is_dup:
                await self.to_grave(card, dest_container)
        else:
            dest_container.add_card(card)

        card.current_row = None
        if hasattr(dest_container, 'row_type'):
            card.current_row = dest_container.row_type

    async def to_row(self, card: CardInstance, source: Optional[CardContainer] = None) -> None:
        """将卡牌放到其默认行"""
        row_type = card.definition.row
        if row_type == RowType.AGILE:
            row_type = RowType.CLOSE
        target_row = self.get_row(card.holder, row_type)
        await self.move_to(card, target_row, source)

    async def to_hand(self, card: CardInstance, source: Optional[CardContainer] = None) -> None:
        await self.move_to(card, "hand", source)

    async def to_grave(self, card: CardInstance, source: Optional[CardContainer] = None) -> None:
        await self.move_to(card, "grave", source)

    async def to_deck(self, card: CardInstance, source: Optional[CardContainer] = None) -> None:
        await self.move_to(card, "deck", source)

    async def to_weather(self, card: CardInstance, source: Optional[CardContainer] = None) -> None:
        await self.move_to(card, "weather", source)

    async def add_card_to_row(
        self,
        card: CardInstance,
        row_name: str,
        player: 'Player',
        source: Optional[CardContainer] = None,
    ) -> None:
        """将卡牌添加到指定玩家的指定行"""
        target_row = self.resolve_row_target(card, row_name, player)
        card.holder = player
        if source is not None:
            source.remove_card(card)
        await target_row.add_card_with_board(card, self)

    async def clear_round(self) -> None:
        """清除一轮的所有卡牌和效果"""
        self.weather.clear_weather(self)
        for row in self.rows.values():
            cards_to_remove = [c for c in row.cards if not c.no_remove]
            if row.special_card is not None and not row.special_card.no_remove:
                cards_to_remove.append(row.special_card)
            # 先清空 effects 和 special_card，再移除卡牌
            # 这样 removed 回调中新增的卡牌会基于干净的 effects 计算分数
            row.effects = RowEffects()
            row.special_card = None
            for card in cards_to_remove:
                await self.to_grave(card, row)
            # 最终同步：确保 total_score 与 cards 中所有剩余卡牌一致
            row.update_scores()

        # 打印 clear_round 完成后的完整 board 状态
        log.debug(self.dump_state())

    def dump_state(self) -> str:
        """返回当前 board 完整状态的格式化字符串，用于日志调试"""
        lines = ["📋 Board State:"]
        # Weather
        weather_cards = [c.name for c in self.weather.cards]
        lines.append(f"  Weather: {weather_cards if weather_cards else '(none)'}")
        # Rows grouped by player
        for (player_id, row_type), row in sorted(self.rows.items(), key=lambda x: (str(x[0][0]), x[0][1].value)):
            player_name = row.owner.name if row.owner else "Unknown"
            cards_info = []
            for c in row.cards:
                cards_info.append(f"{c.name}({c.current_strength})")
            special_info = f"special={row.special_card.name}" if row.special_card else "special=(none)"
            effects_str = (
                f"w={row.effects.weather} hw={row.effects.half_weather} "
                f"h={row.effects.horn} m={row.effects.morale} md={row.effects.mardroeme} "
                f"bond={row.effects.bond}"
            )
            lines.append(
                f"  [{player_name}_{row_type.value}] total={row.total_score} "
                f"cards=[{', '.join(cards_info)}] {special_info} effects=({effects_str})"
            )
        return "\n".join(lines)


# ============================================================================
# Ability Handler Interface
# ============================================================================

class AbilityHandler:
    """能力处理器基类（具体能力在 abilities.py 中实现）"""

    async def on_placed(self, card: CardInstance, row: BoardRow, board: Board) -> None:
        pass

    async def on_removed(self, card: CardInstance, board: Board) -> None:
        pass

    async def on_activated(self, card: CardInstance, board: Board) -> None:
        pass

    def calculate_weight(self, card: CardInstance, ai_context: Any) -> float:
        return 1.0
