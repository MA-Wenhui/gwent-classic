"""
卡牌能力处理器实现
对应 JS abilities.js 中的 ability_dict
"""

from __future__ import annotations
import logging
import random
from typing import Dict, Optional, Callable, Any, TYPE_CHECKING

from .enums import AbilityType, RowType
from .card import CardDefinition, CardInstance
from .board import BoardRow, Board

log = logging.getLogger("gwent.abilities")

if TYPE_CHECKING:
    from .player import Player
    from .game_state import GameState


# ============================================================================
# 卡牌定义注册表（用于 avenger 等需要按 ID 创建新卡的场景）
# ============================================================================

_card_registry: Dict[int, CardDefinition] = {}


def register_card_definitions(definitions: list[CardDefinition]) -> None:
    """注册所有卡牌定义到全局注册表"""
    global _card_registry
    _card_registry = {d.id: d for d in definitions}


def get_card_definition(card_id: int) -> Optional[CardDefinition]:
    return _card_registry.get(card_id)


# ============================================================================
# 能力回调工厂
# ============================================================================

def build_placed_callbacks(card: CardInstance) -> list[Callable]:
    """根据卡牌能力构建 placed 回调列表"""
    callbacks = []
    for ability in card.abilities:
        handler = _PLACED_HANDLERS.get(ability)
        if handler is not None:
            callbacks.append(handler)
    return callbacks


def build_removed_callbacks(card: CardInstance) -> list[Callable]:
    """根据卡牌能力构建 removed 回调列表"""
    callbacks = []
    for ability in card.abilities:
        handler = _REMOVED_HANDLERS.get(ability)
        if handler is not None:
            callbacks.append(handler)
    return callbacks


# ============================================================================
# Placed Handlers - 放置时触发
# ============================================================================

async def _on_horn_placed(card: CardInstance, row: BoardRow) -> None:
    """Commander's Horn: 行效果已在 update_state 中处理"""
    pass


async def _on_mardroeme_placed(card: CardInstance, row: BoardRow) -> None:
    """Mardroeme: 触发同行所有 Berserker 变形"""
    berserkers = row.find_cards(lambda c: c.has_ability(AbilityType.BERSERKER))
    log.info(f"  🔮 Mardroeme triggers {len(berserkers)} berserker(s) in {row.name}")
    for berserker in berserkers:
        await _transform_berserker(berserker, row)


async def _transform_berserker(card: CardInstance, row: BoardRow) -> None:
    """Berserker 变形逻辑：移除原卡，创建变形后的新卡加入行"""
    if card.is_transformed:
        return
    log.info(f"  🐻 Berserker transform: {card.name} (base={card.definition.base_strength})")
    card.is_transformed = True

    # Young Berserker (base=2) → id=207, Berserker (base=4) → id=206
    new_card_id = 207 if card.definition.base_strength == 2 else 206
    new_def = get_card_definition(new_card_id)
    if new_def is None:
        return

    # 从行中移除原卡
    row.remove_card(card)
    row.update_state(card, False)

    # 创建新卡并加入行
    new_card = CardInstance(definition=new_def, holder=card.holder)
    new_card.placed_callbacks = build_placed_callbacks(new_card)
    new_card.removed_callbacks = build_removed_callbacks(new_card)
    row.add_card(new_card)
    row.update_state(new_card, True)


async def _on_berserker_placed(card: CardInstance, row: BoardRow) -> None:
    """Berserker: 如果行上有 Mardroeme 则立即变形"""
    if row.effects.mardroeme > 0:
        await _transform_berserker(card, row)


async def _on_scorch_placed(card: CardInstance, row: BoardRow) -> None:
    """Scorch: 摧毁全场战力最高的行中所有最强单位
    JS 逻辑：先临时移除自身再计算各行 maxUnits，避免自身影响比较"""
    if card.holder is None or card.holder.board is None:
        return
    board = card.holder.board

    # 如果 scorch 卡在某个行上，临时移除以排除自身影响
    source_row = None
    if row is not None and card in row.cards:
        source_row = row
        row.remove_card(card)
        row.update_state(card, False)
        row.update_scores(board.game.double_spy_power)

    all_rows = list(board.rows.values())
    if not all_rows:
        if source_row is not None:
            source_row.add_card(card)
            source_row.update_state(card, True)
            source_row.update_scores(board.game.double_spy_power)
        return

    # 找每行最强单位，取全局最高战力
    row_max_units = []
    for target_row in all_rows:
        max_units = target_row.get_max_units()
        if max_units:
            row_max_units.append((target_row, max_units))

    if not row_max_units:
        if source_row is not None:
            source_row.add_card(card)
            source_row.update_state(card, True)
            source_row.update_scores(board.game.double_spy_power)
        return

    global_max_power = max(units[0].current_strength for _, units in row_max_units)
    scorched = [(r, u) for r, units in row_max_units for u in units if u.current_strength == global_max_power]

    for target_row, unit in scorched:
        await board.to_grave(unit, target_row)

    # 恢复 scorch 卡到原行（之后会被 game_engine 移入墓地）
    if source_row is not None:
        source_row.add_card(card)
        source_row.update_state(card, True)
        source_row.update_scores(board.game.double_spy_power)


async def _on_scorch_c_placed(card: CardInstance, row: BoardRow) -> None:
    """Scorch Close: 摧毁对手近战行最强单位（总分>=10时）"""
    if card.holder is None or card.holder.board is None or card.holder.opponent is None:
        return
    target_row = card.holder.board.get_row(card.holder.opponent, RowType.CLOSE)
    await execute_scorch(card.holder.board, target_row)


async def _on_scorch_r_placed(card: CardInstance, row: BoardRow) -> None:
    """Scorch Ranged: 摧毁对手远程行最强单位（总分>=10时）"""
    if card.holder is None or card.holder.board is None or card.holder.opponent is None:
        return
    target_row = card.holder.board.get_row(card.holder.opponent, RowType.RANGED)
    await execute_scorch(card.holder.board, target_row)


async def _on_scorch_s_placed(card: CardInstance, row: BoardRow) -> None:
    """Scorch Siege: 摧毁对手攻城行最强单位（总分>=10时）"""
    if card.holder is None or card.holder.board is None or card.holder.opponent is None:
        return
    target_row = card.holder.board.get_row(card.holder.opponent, RowType.SIEGE)
    await execute_scorch(card.holder.board, target_row)


async def _on_muster_placed(card: CardInstance, row: BoardRow) -> None:
    """Muster: 从手牌和牌堆召唤同名卡"""
    if card.holder is None or card.holder.board is None:
        return
    await execute_muster(card, card.holder.board)


async def _on_spy_placed(card: CardInstance, row: BoardRow) -> None:
    """Spy: 抽2张牌，holder 切换为对手"""
    if card.holder is None or card.holder.board is None:
        return
    await execute_spy(card, card.holder.board)


async def _on_medic_placed(card: CardInstance, row: BoardRow) -> None:
    """Medic: 从墓地复活一个非英雄单位"""
    if card.holder is None or card.holder.board is None:
        return
    game_state = card.holder.board.game
    await execute_medic(card, card.holder.board, game_state)


async def _on_morale_placed(card: CardInstance, row: BoardRow) -> None:
    """Morale: 行效果已在 update_state 中处理，无需额外操作"""
    pass


async def _on_bond_placed(card: CardInstance, row: BoardRow) -> None:
    """Tight Bond: 行效果已在 update_state 中处理，无需额外操作"""
    pass


async def _on_francesca_daisy_placed(card: CardInstance, row: BoardRow) -> None:
    """Francesca Daisy: 注册 gameStart 钩子，开局额外抽一张牌"""
    if card.holder is None or card.holder.board is None:
        return
    player = card.holder

    def draw_extra():
        player.deck.draw(player.hand, 1)

    card.holder.board.game.game_start_hooks.append(draw_extra)


async def _on_king_bran_placed(card: CardInstance, row: BoardRow) -> None:
    """King Bran: 己方所有行天气减半"""
    if card.holder is None or card.holder.board is None:
        return
    for player_row in card.holder.board.get_player_rows(card.holder):
        player_row.effects.half_weather = True


async def _on_vildkarrl_morale_placed(card: CardInstance, row: BoardRow) -> None:
    """Vildkaarl Morale: 变形后的 Vildkaarl 带有 morale 能力
    JS 中 vildkarrl placed 会移除自身 vildkarrl 能力标记，延迟后移除回调。
    Python 中变形已替换为新卡实例，新卡的 morale 能力由 update_state 自动处理。"""
    pass


async def _on_vildkarrl_bond_placed(card: CardInstance, row: BoardRow) -> None:
    """Vildkaarl Bond: 变形后的 Vildkaarl 带有 bond 能力
    同上，bond 效果由 update_state 自动处理。"""
    pass


async def _on_vildkarrl_placed(card: CardInstance, row: BoardRow) -> None:
    """Vildkaarl (未变形): JS 中移除 vildkarrl 能力标记并延迟移除回调。
    Python 中此回调仅在卡牌仍持有 vildkarrl 能力时触发（即尚未被 berserker 变形替换）。
    实际变形由 _on_berserker_placed / _on_mardroeme_placed 处理。"""
    pass


_PLACED_HANDLERS: Dict[AbilityType, Callable] = {
    AbilityType.HORN: _on_horn_placed,
    AbilityType.MARDROEME: _on_mardroeme_placed,
    AbilityType.BERSERKER: _on_berserker_placed,
    AbilityType.SCORCH: _on_scorch_placed,
    AbilityType.SCORCH_C: _on_scorch_c_placed,
    AbilityType.SCORCH_R: _on_scorch_r_placed,
    AbilityType.SCORCH_S: _on_scorch_s_placed,
    AbilityType.MUSTER: _on_muster_placed,
    AbilityType.SPY: _on_spy_placed,
    AbilityType.MEDIC: _on_medic_placed,
    AbilityType.MORALE: _on_morale_placed,
    AbilityType.BOND: _on_bond_placed,
    AbilityType.FRANCESCA_DAISY: _on_francesca_daisy_placed,
    AbilityType.KING_BRAN: _on_king_bran_placed,
    AbilityType.VILDKAARL_MORALE: _on_vildkarrl_morale_placed,
    AbilityType.VILDKAARL_BOND: _on_vildkarrl_bond_placed,
}


# ============================================================================
# Removed Handlers - 移除时触发
# ============================================================================

async def _on_avenger_removed(card: CardInstance) -> None:
    """Avenger: 被移除时召唤 BDF (id=21) 到近战行"""
    if card.holder is None or card.holder.board is None:
        return
    log.info(f"  ⚔️  Avenger triggered: {card.name} summons BDF")
    bdf_def = get_card_definition(21)
    if bdf_def is None:
        return
    bdf = CardInstance(definition=bdf_def, holder=card.holder)
    # BDF 被移除后自动进墓地
    async def auto_grave(c: CardInstance) -> None:
        if c.holder and c.holder.board:
            await c.holder.board.to_grave(c)
    bdf.removed_callbacks.append(auto_grave)
    await card.holder.board.add_card_to_row(bdf, "close", card.holder)


async def _on_avenger_kambi_removed(card: CardInstance) -> None:
    """Avenger Kambi: 被移除时召唤 Hemdall (id=196) 到近战行"""
    if card.holder is None or card.holder.board is None:
        return
    hemdall_def = get_card_definition(196)
    if hemdall_def is None:
        return
    hemdall = CardInstance(definition=hemdall_def, holder=card.holder)
    async def auto_grave(c: CardInstance) -> None:
        if c.holder and c.holder.board:
            await c.holder.board.to_grave(c)
    hemdall.removed_callbacks.append(auto_grave)
    await card.holder.board.add_card_to_row(hemdall, "close", card.holder)


_REMOVED_HANDLERS: Dict[AbilityType, Callable] = {
    AbilityType.AVENGER: _on_avenger_removed,
    AbilityType.AVENGER_KAMBI: _on_avenger_kambi_removed,
}


# ============================================================================
# Leader Activated Handlers - 领袖能力激活
# ============================================================================

class LeaderAbility:
    """领袖能力封装"""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    async def activate(self, card: CardInstance, board: Board) -> None:
        pass

    def calculate_weight(self, card: CardInstance, ai_context: Any) -> float:
        return 0.0


class FoltestKingAbility(LeaderAbility):
    """Foltest King: 从牌堆打出 Impenetrable Fog"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        fog_card = card.holder.deck.find_card(lambda c: c.name == "Impenetrable Fog")
        if fog_card:
            card.holder.deck.remove_card(fog_card)
            await board.to_weather(fog_card)


class FoltestLordAbility(LeaderAbility):
    """Foltest Lord: 清除所有天气"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        board.weather.clear_weather(board)


class FoltestSiegemasterAbility(LeaderAbility):
    """Foltest Siegemaster: 攻城行号角效果"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        siege_row = board.get_row(card.holder, RowType.SIEGE)
        if siege_row.special_card is None:
            horn_def = get_card_definition(5)
            if horn_def:
                horn = CardInstance(definition=horn_def)
                siege_row.special_card = horn
                siege_row.effects.horn += 1
                siege_row.update_scores(board.game.double_spy_power)


class FoltestSteelforgedAbility(LeaderAbility):
    """Foltest Steelforged: 灼烧对手攻城行"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        opponent = card.holder.opponent
        if opponent is None:
            return
        siege_row = board.get_row(opponent, RowType.SIEGE)
        if siege_row.total_score >= 10:
            max_units = siege_row.get_max_units()
            for unit in max_units:
                await board.to_grave(unit, siege_row)


class FoltestSonAbility(LeaderAbility):
    """Foltest Son: 灼烧对手远程行"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        opponent = card.holder.opponent
        if opponent is None:
            return
        ranged_row = board.get_row(opponent, RowType.RANGED)
        if ranged_row.total_score >= 10:
            max_units = ranged_row.get_max_units()
            for unit in max_units:
                await board.to_grave(unit, ranged_row)


class EmhyrImperialAbility(LeaderAbility):
    """Emhyr Imperial: 从牌堆打出 Torrential Rain"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        rain_card = card.holder.deck.find_card(lambda c: c.name == "Torrential Rain")
        if rain_card:
            card.holder.deck.remove_card(rain_card)
            await board.to_weather(rain_card)


class EmhyrEmperorAbility(LeaderAbility):
    """Emhyr Emperor: 查看对手3张随机手牌（纯信息，无状态变更）"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        pass


class EmhyrWhiteflameAbility(LeaderAbility):
    """Emhyr Whiteflame: 取消对手领袖能力（在游戏初始化时处理）"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        pass


class EmhyrRelentlessAbility(LeaderAbility):
    """Emhyr Relentless: 从对手墓地拿一张单位到手牌"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        opponent = card.holder.opponent
        if opponent is None:
            return
        units = opponent.grave.find_cards(lambda c: c.is_unit)
        if not units:
            return
        chosen = units[random.randint(0, len(units) - 1)]
        opponent.grave.remove_card(chosen)
        chosen.holder = card.holder
        card.holder.hand.add_card(chosen)


class EmhyrInvaderAbility(LeaderAbility):
    """Emhyr Invader: 设置随机复活模式"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        board.game.random_respawn = True


class EredinCommanderAbility(LeaderAbility):
    """Eredin Commander: 近战行号角效果"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        close_row = board.get_row(card.holder, RowType.CLOSE)
        if close_row.special_card is None:
            horn_def = get_card_definition(5)
            if horn_def:
                horn = CardInstance(definition=horn_def)
                close_row.special_card = horn
                close_row.effects.horn += 1
                close_row.update_scores(board.game.double_spy_power)


class EredinBringerOfDeathAbility(LeaderAbility):
    """Eredin Bringer of Death: 从墓地拿一张单位到手牌"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        units = card.holder.grave.find_cards(lambda c: c.is_unit)
        if not units:
            return
        chosen = units[random.randint(0, len(units) - 1)]
        card.holder.grave.remove_card(chosen)
        card.holder.hand.add_card(chosen)


class EredinDestroyerAbility(LeaderAbility):
    """Eredin Destroyer: 弃2张牌，从牌堆抽1张"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        hand_cards = list(card.holder.hand.cards)
        discardable = [c for c in hand_cards if c.definition.base_strength < 7]
        to_discard = discardable[:2] if len(discardable) >= 2 else hand_cards[:2]
        for c in to_discard:
            await board.to_grave(c, card.holder.hand)
        card.holder.deck.draw(card.holder.hand, 1)


class EredinKingAbility(LeaderAbility):
    """Eredin King: 从牌堆打出一张天气卡"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        weather_cards = card.holder.deck.find_cards(
            lambda c: c.definition.faction.value == "weather"
        )
        if not weather_cards:
            return
        chosen = weather_cards[random.randint(0, len(weather_cards) - 1)]
        card.holder.deck.remove_card(chosen)
        await board.to_weather(chosen)


class EredinTreacherousAbility(LeaderAbility):
    """Eredin Treacherous: 间谍战力翻倍"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        board.game.double_spy_power = True


class FrancescaQueenAbility(LeaderAbility):
    """Francesca Queen: 灼烧对手近战行"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        opponent = card.holder.opponent
        if opponent is None:
            return
        close_row = board.get_row(opponent, RowType.CLOSE)
        if close_row.total_score >= 10:
            max_units = close_row.get_max_units()
            for unit in max_units:
                await board.to_grave(unit, close_row)


class FrancescaBeautifulAbility(LeaderAbility):
    """Francesca Beautiful: 远程行号角效果"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        ranged_row = board.get_row(card.holder, RowType.RANGED)
        if ranged_row.special_card is None:
            horn_def = get_card_definition(5)
            if horn_def:
                horn = CardInstance(definition=horn_def)
                ranged_row.special_card = horn
                ranged_row.effects.horn += 1
                ranged_row.update_scores(board.game.double_spy_power)


class FrancescaDaisyAbility(LeaderAbility):
    """Francesca Daisy: 游戏开始时额外抽一张"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        card.holder.deck.draw(card.holder.hand, 1)


class FrancescaPurebloodAbility(LeaderAbility):
    """Francesca Pureblood: 从牌堆打出 Biting Frost"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        frost_card = card.holder.deck.find_card(lambda c: c.name == "Biting Frost")
        if frost_card:
            card.holder.deck.remove_card(frost_card)
            await board.to_weather(frost_card)


class FrancescaHopeAbility(LeaderAbility):
    """Francesca Hope: 优化敏捷单位所在行使总分最大"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        close_row = board.get_row(card.holder, RowType.CLOSE)
        ranged_row = board.get_row(card.holder, RowType.RANGED)

        agile_in_close = [c for c in close_row.cards if c.definition.row == RowType.AGILE]
        agile_in_ranged = [c for c in ranged_row.cards if c.definition.row == RowType.AGILE]
        all_agile = agile_in_close + agile_in_ranged

        if not all_agile:
            return

        best_score = close_row.calculate_score() + ranged_row.calculate_score()
        best_pattern = [0] * len(all_agile)

        for mask in range(1 << len(all_agile)):
            close_copy = close_row.get_virtual_copy(lambda c: c.definition.row != RowType.AGILE)
            ranged_copy = ranged_row.get_virtual_copy(lambda c: c.definition.row != RowType.AGILE)
            pattern = []
            for i, agile_card in enumerate(all_agile):
                cloned = agile_card.clone()
                if mask & (1 << i):
                    ranged_copy.add_card(cloned)
                    ranged_copy.update_state(cloned, True)
                    pattern.append(1)
                else:
                    close_copy.add_card(cloned)
                    close_copy.update_state(cloned, True)
                    pattern.append(0)
            score = close_copy.calculate_score() + ranged_copy.calculate_score()
            if score > best_score:
                best_score = score
                best_pattern = pattern

        for i, agile_card in enumerate(all_agile):
            currently_in_close = agile_card in close_row.cards
            should_be_in_close = best_pattern[i] == 0
            if currently_in_close != should_be_in_close:
                source_row = close_row if currently_in_close else ranged_row
                dest_row = ranged_row if currently_in_close else close_row
                source_row.remove_card(agile_card)
                source_row.update_state(agile_card, False)
                dest_row.add_card(agile_card)
                dest_row.update_state(agile_card, True)

        double_spy = board.game.double_spy_power
        close_row.update_scores(double_spy)
        ranged_row.update_scores(double_spy)


class CrachAnCraiteAbility(LeaderAbility):
    """Crach an Craite: 双方墓地洗牌回牌堆"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        for grave_card in list(card.holder.grave.cards):
            card.holder.grave.remove_card(grave_card)
            card.holder.deck.add_card(grave_card)
        card.holder.deck.shuffle()

        opponent = card.holder.opponent
        if opponent:
            for grave_card in list(opponent.grave.cards):
                opponent.grave.remove_card(grave_card)
                opponent.deck.add_card(grave_card)
            opponent.deck.shuffle()


class KingBranAbility(LeaderAbility):
    """King Bran: 己方行天气减半（placed 已处理，activated 为空）"""

    async def activate(self, card: CardInstance, board: Board) -> None:
        pass


# ============================================================================
# Leader Ability Registry
# ============================================================================

LEADER_ABILITIES: Dict[str, LeaderAbility] = {
    "foltest_king": FoltestKingAbility("Foltest King", "Pick an Impenetrable Fog card from your deck and play it instantly."),
    "foltest_lord": FoltestLordAbility("Foltest Lord", "Clear any weather effects in play."),
    "foltest_siegemaster": FoltestSiegemasterAbility("Foltest Siegemaster", "Doubles the strength of all your Siege units."),
    "foltest_steelforged": FoltestSteelforgedAbility("Foltest Steelforged", "Destroy enemy's strongest Siege unit(s) if total >= 10."),
    "foltest_son": FoltestSonAbility("Foltest Son", "Destroy enemy's strongest Ranged unit(s) if total >= 10."),
    "emhyr_imperial": EmhyrImperialAbility("Emhyr Imperial", "Pick a Torrential Rain card from your deck and play it instantly."),
    "emhyr_emperor": EmhyrEmperorAbility("Emhyr Emperor", "Look at 3 random cards from your opponent's hand."),
    "emhyr_whiteflame": EmhyrWhiteflameAbility("Emhyr Whiteflame", "Cancel your opponent's Leader Ability."),
    "emhyr_relentless": EmhyrRelentlessAbility("Emhyr Relentless", "Draw a card from your opponent's discard pile."),
    "emhyr_invader": EmhyrInvaderAbility("Emhyr Invader", "Abilities that restore a unit restore a randomly-chosen unit."),
    "eredin_commander": EredinCommanderAbility("Eredin Commander", "Double the strength of all your Close Combat units."),
    "eredin_bringer_of_death": EredinBringerOfDeathAbility("Eredin Bringer of Death", "Restore a card from your discard pile to your hand."),
    "eredin_destroyer": EredinDestroyerAbility("Eredin Destroyer", "Discard 2 cards and draw 1 card from your deck."),
    "eredin_king": EredinKingAbility("Eredin King", "Pick any weather card from your deck and play it instantly."),
    "eredin_treacherous": EredinTreacherousAbility("Eredin Treacherous", "Doubles the strength of all spy cards."),
    "francesca_queen": FrancescaQueenAbility("Francesca Queen", "Destroy enemy's strongest Close Combat unit(s) if total >= 10."),
    "francesca_beautiful": FrancescaBeautifulAbility("Francesca Beautiful", "Doubles the strength of all your Ranged Combat units."),
    "francesca_daisy": FrancescaDaisyAbility("Francesca Daisy", "Draw an extra card at the beginning of the battle."),
    "francesca_pureblood": FrancescaPurebloodAbility("Francesca Pureblood", "Pick a Biting Frost card from your deck and play it instantly."),
    "francesca_hope": FrancescaHopeAbility("Francesca Hope", "Move agile units to whichever valid row maximizes their strength."),
    "crach_an_craite": CrachAnCraiteAbility("Crach an Craite", "Shuffle all cards from each player's graveyard back into their decks."),
    "king_bran": KingBranAbility("King Bran", "Units only lose half their Strength in bad weather conditions."),
}


def get_leader_ability(ability_key: str) -> Optional[LeaderAbility]:
    return LEADER_ABILITIES.get(ability_key)


# ============================================================================
# Scorch / Muster / Spy / Medic 的完整实现（需要 Board 引用）
# ============================================================================

async def execute_scorch(board: Board, target_row: BoardRow) -> None:
    """执行灼烧：如果行总分>=10，摧毁最强单位"""
    if target_row.total_score < 10:
        return
    max_units = target_row.get_max_units()
    for unit in max_units:
        await board.to_grave(unit, target_row)


async def execute_muster(card: CardInstance, board: Board) -> None:
    """执行集结：从手牌和牌堆召唤同名卡"""
    holder = card.holder
    if holder is None:
        return

    name = card.name
    dash_idx = name.find('-')
    card_name = name[:dash_idx].strip() if dash_idx != -1 else name

    def name_matches(c: CardInstance) -> bool:
        return c.name.startswith(card_name)

    from_hand = holder.hand.get_cards(name_matches)
    from_deck = holder.deck.get_cards(name_matches)

    for summoned in from_hand + from_deck:
        row_type = summoned.definition.row
        if row_type == RowType.AGILE:
            row_type = RowType.CLOSE
        if row_type in (RowType.CLOSE, RowType.RANGED, RowType.SIEGE):
            await board.add_card_to_row(summoned, row_type.value, holder)


async def execute_spy(card: CardInstance, board: Board) -> None:
    """执行间谍：抽2张牌，holder 切换为对手"""
    holder = card.holder
    if holder is None:
        return
    for _ in range(2):
        if len(holder.deck.cards) > 0:
            holder.deck.draw(holder.hand, 1)
    card.holder = holder.opponent


async def execute_medic(card: CardInstance, board: Board, game_state: 'GameState') -> None:
    """执行医生：从墓地复活一个非英雄非特殊单位"""
    holder = card.holder
    if holder is None:
        return

    units = holder.grave.find_cards(lambda c: c.is_unit and not c.is_hero)
    if not units:
        return

    if game_state.random_respawn:
        chosen = units[random.randint(0, len(units) - 1)]
    else:
        chosen = units[random.randint(0, len(units) - 1)]

    holder.grave.remove_card(chosen)

    row_type = chosen.definition.row
    if row_type == RowType.AGILE:
        close_row = board.get_row(holder, RowType.CLOSE)
        ranged_row = board.get_row(holder, RowType.RANGED)
        close_virtual = close_row.get_virtual_copy()
        ranged_virtual = ranged_row.get_virtual_copy()
        close_clone = chosen.clone()
        ranged_clone = chosen.clone()
        close_virtual.add_card(close_clone)
        close_virtual.update_state(close_clone, True)
        ranged_virtual.add_card(ranged_clone)
        ranged_virtual.update_state(ranged_clone, True)
        close_diff = close_virtual.calculate_score() - close_row.calculate_score()
        ranged_diff = ranged_virtual.calculate_score() - ranged_row.calculate_score()
        if close_diff > ranged_diff:
            row_type = RowType.CLOSE
        elif ranged_diff > close_diff:
            row_type = RowType.RANGED
        else:
            row_type = RowType.CLOSE if random.random() < 0.5 else RowType.RANGED

    if row_type in (RowType.CLOSE, RowType.RANGED, RowType.SIEGE):
        await board.add_card_to_row(chosen, row_type.value, holder)
