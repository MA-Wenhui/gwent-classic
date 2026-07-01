"""战场行、天气系统与 Board 状态规则验证测试"""

import asyncio
import random
from conftest import (
    make_card, create_game_state, create_engine_with_decks, simulate_random_game,
    load_decks, deck_to_args, CARDS_PATH,
    CardDefinition, CardInstance, Faction, RowType, AbilityType,
    BoardRow, RowEffects, WeatherZone, Player, GameState, Board, GameEngine,
)


# ============================================================================
# BoardRow 基础效果测试
# ============================================================================

def test_row_score_basic():
    row = BoardRow(RowType.CLOSE)
    c1 = make_card("A", 5)
    c2 = make_card("B", 3)
    row.add_card(c1)
    row.update_state(c1, True)
    row.add_card(c2)
    row.update_state(c2, True)
    assert row.calculate_score() == 8
    print("  ✅ Basic row score")


def test_row_horn():
    row = BoardRow(RowType.CLOSE)
    c1 = make_card("A", 5)
    row.add_card(c1)
    row.update_state(c1, True)
    assert row.calculate_score() == 5
    row.effects.horn = 1
    assert row.calculate_score() == 10
    print("  ✅ Horn effect")


def test_row_weather():
    row = BoardRow(RowType.CLOSE)
    c1 = make_card("A", 10)
    c2 = make_card("Hero", 10, hero=True)
    row.add_card(c1)
    row.update_state(c1, True)
    row.add_card(c2)
    row.update_state(c2, True)
    row.effects.weather = True
    score = row.calculate_score()
    assert score == 11, f"Expected 11, got {score}"
    print("  ✅ Weather effect")


def test_row_morale():
    row = BoardRow(RowType.CLOSE)
    c1 = make_card("Morale", 4, abilities=(AbilityType.MORALE,))
    c2 = make_card("Unit", 3)
    row.add_card(c1)
    row.update_state(c1, True)
    row.add_card(c2)
    row.update_state(c2, True)
    score = row.calculate_score()
    assert score == 8, f"Expected 8, got {score}"
    print("  ✅ Morale effect")


def test_row_bond():
    row = BoardRow(RowType.CLOSE)
    d = CardDefinition(id=100, name="Bond", faction=Faction.NEUTRAL,
                       row=RowType.CLOSE, base_strength=4,
                       abilities=(AbilityType.BOND,))
    c1 = CardInstance(definition=d)
    c2 = CardInstance(definition=d)
    row.add_card(c1)
    row.update_state(c1, True)
    row.add_card(c2)
    row.update_state(c2, True)
    score = row.calculate_score()
    assert score == 16, f"Expected 16, got {score}"
    print("  ✅ Bond effect")


def test_virtual_copy():
    row = BoardRow(RowType.CLOSE)
    c1 = make_card("A", 5)
    row.add_card(c1)
    row.update_state(c1, True)
    row.effects.horn = 1
    virtual = row.get_virtual_copy()
    assert virtual.effects.horn == 1
    assert len(virtual.cards) == 1
    assert virtual.cards[0] is not c1
    print("  ✅ Virtual copy")


async def test_weather_zone():
    _, board, _, _ = create_game_state()
    wz = board.weather

    frost_def = CardDefinition(id=4, name="Biting Frost", faction=Faction.WEATHER,
                               row=RowType.WEATHER, base_strength=0,
                               abilities=(AbilityType.FROST,))
    frost = CardInstance(definition=frost_def)
    is_dup = wz.add_weather_card(frost, board)
    assert not is_dup
    assert wz.type_counts["frost"] == 1
    print("  ✅ WeatherZone")


# ============================================================================
# BoardValidator - 对局中每步验证 board 状态规则
# ============================================================================

class BoardValidator:
    """Board 状态规则验证器"""

    def __init__(self, engine: GameEngine):
        self.engine = engine
        self.errors = []

    def validate_all(self, context: str = "") -> bool:
        self.errors = []
        self._check_special_card_limit()
        self._check_hero_immunity()
        self._check_weather_effect()
        self._check_spy_placement()
        self._check_bond_multiplier()
        self._check_horn_multiplier()
        self._check_morale_bonus()
        self._check_mardroeme_effect()
        self._check_row_score_consistency()
        self._check_decoy_zero_power()
        self._check_card_holder_consistency()
        self._check_effects_consistency()
        self._check_berserker_transform_state()

        if self.errors:
            prefix = f"[{context}] " if context else ""
            for err in self.errors:
                print(f"  ❌ {prefix}{err}")
            return False
        return True

    def _check_special_card_limit(self):
        special_names = {"Commander's Horn", "Mardroeme"}
        for key, row in self.engine.board.rows.items():
            special_in_cards = [c for c in row.cards if c.name in special_names]
            if special_in_cards:
                self.errors.append(
                    f"Row {row.name} has special card(s) in cards list: {[c.name for c in special_in_cards]}"
                )
            if row.special_card is not None and row.special_card.name not in special_names:
                self.errors.append(
                    f"Row {row.name} special_card={row.special_card.name} is not Commander's Horn/Mardroeme"
                )

    def _check_hero_immunity(self):
        for key, row in self.engine.board.rows.items():
            for card in row.cards:
                if card.is_hero and card.current_strength != card.definition.base_strength:
                    self.errors.append(
                        f"Hero {card.name} in {row.name}: strength={card.current_strength}, "
                        f"expected base={card.definition.base_strength}"
                    )

    def _check_weather_effect(self):
        for key, row in self.engine.board.rows.items():
            if not row.effects.weather:
                continue
            double_spy = self.engine.game_state.double_spy_power if self.engine.game_state else False
            for card in row.cards:
                if card.name == "Decoy":
                    continue
                expected = row.calculate_card_score(card, double_spy)
                if card.current_strength != expected:
                    self.errors.append(
                        f"Weather row {row.name}: {card.name} strength={card.current_strength}, expected={expected}"
                    )

    def _check_spy_placement(self):
        for key, row in self.engine.board.rows.items():
            for card in row.cards:
                if card.has_ability(AbilityType.SPY) and card.holder is not None:
                    if row.owner is not None and row.owner != card.holder:
                        self.errors.append(
                            f"Spy {card.name} in {row.name}: holder={card.holder.name}, row_owner={row.owner.name}"
                        )

    def _check_bond_multiplier(self):
        for key, row in self.engine.board.rows.items():
            if not any(v > 1 for v in row.effects.bond.values()):
                continue
            double_spy = self.engine.game_state.double_spy_power if self.engine.game_state else False
            for card in row.cards:
                if card.name == "Decoy":
                    continue
                expected = row.calculate_card_score(card, double_spy)
                if card.current_strength != expected:
                    self.errors.append(
                        f"Bond row {row.name}: {card.name} strength={card.current_strength}, expected={expected}"
                    )

    def _check_horn_multiplier(self):
        for key, row in self.engine.board.rows.items():
            if row.effects.horn <= 0:
                continue
            double_spy = self.engine.game_state.double_spy_power if self.engine.game_state else False
            for card in row.cards:
                if card.name == "Decoy":
                    continue
                expected = row.calculate_card_score(card, double_spy)
                if card.current_strength != expected:
                    self.errors.append(
                        f"Horn row {row.name}: {card.name} strength={card.current_strength}, expected={expected}"
                    )

    def _check_morale_bonus(self):
        for key, row in self.engine.board.rows.items():
            if row.effects.morale <= 0:
                continue
            double_spy = self.engine.game_state.double_spy_power if self.engine.game_state else False
            for card in row.cards:
                if card.name == "Decoy":
                    continue
                expected = row.calculate_card_score(card, double_spy)
                if card.current_strength != expected:
                    self.errors.append(
                        f"Morale row {row.name}: {card.name} strength={card.current_strength}, expected={expected}"
                    )

    def _check_mardroeme_effect(self):
        for key, row in self.engine.board.rows.items():
            if row.effects.mardroeme <= 0:
                continue
            double_spy = self.engine.game_state.double_spy_power if self.engine.game_state else False
            for card in row.cards:
                if card.name == "Decoy":
                    continue
                expected = row.calculate_card_score(card, double_spy)
                if card.current_strength != expected:
                    self.errors.append(
                        f"Mardroeme row {row.name}: {card.name} strength={card.current_strength}, expected={expected}"
                    )

    def _check_row_score_consistency(self):
        for key, row in self.engine.board.rows.items():
            calculated = sum(c.current_strength for c in row.cards)
            if row.total_score != calculated:
                self.errors.append(
                    f"Row {row.name}: total_score={row.total_score}, sum_of_cards={calculated}"
                )

    def _check_decoy_zero_power(self):
        for key, row in self.engine.board.rows.items():
            for card in row.cards:
                if card.name == "Decoy" and card.current_strength != 0:
                    self.errors.append(f"Decoy in {row.name}: strength={card.current_strength}, expected 0")

    def _check_card_holder_consistency(self):
        for key, row in self.engine.board.rows.items():
            if row.owner is None:
                continue
            for card in row.cards:
                if card.has_ability(AbilityType.SPY):
                    continue
                if card.holder is not None and card.holder != row.owner:
                    self.errors.append(
                        f"Card {card.name} in {row.name}: holder={card.holder.name}, row_owner={row.owner.name}"
                    )

    def _check_effects_consistency(self):
        for key, row in self.engine.board.rows.items():
            horn_cards = [c for c in row.cards if c.has_ability(AbilityType.HORN)]
            horn_special = (row.special_card is not None and row.special_card.name == "Commander's Horn")
            if row.effects.horn > 0 and not (horn_cards or horn_special):
                self.errors.append(f"Row {row.name}: effects.horn={row.effects.horn} but no horn source")

            if row.effects.mardroeme > 0:
                has_mardroeme = (row.special_card is not None and row.special_card.name == "Mardroeme")
                if not has_mardroeme:
                    self.errors.append(f"Row {row.name}: effects.mardroeme={row.effects.mardroeme} but no Mardroeme")

            morale_cards = [c for c in row.cards
                          if c.has_ability(AbilityType.MORALE) or c.has_ability(AbilityType.VILDKAARL_MORALE)]
            if row.effects.morale > 0 and not morale_cards:
                self.errors.append(f"Row {row.name}: effects.morale={row.effects.morale} but no morale source")

            for bond_name, bond_count in row.effects.bond.items():
                if bond_count > 1:
                    matching = [c for c in row.cards if c.name == bond_name]
                    if len(matching) < bond_count:
                        self.errors.append(
                            f"Row {row.name}: bond[{bond_name}]={bond_count} but only {len(matching)} matching cards"
                        )

    def _check_berserker_transform_state(self):
        for key, row in self.engine.board.rows.items():
            for card in row.cards:
                if card.is_transformed and card.has_ability(AbilityType.BERSERKER):
                    self.errors.append(f"Transformed {card.name} in {row.name} still has BERSERKER ability")


async def test_board_validation_during_game():
    """完整对局中每步操作后验证 board 状态"""
    decks = load_decks()
    total_checks = 0
    total_errors = 0
    matchup_count = 0

    for i in range(len(decks)):
        for j in range(i + 1, len(decks)):
            engine = GameEngine(CARDS_PATH)
            p1_f, p1_l, p1_c = deck_to_args(decks[i])
            p2_f, p2_l, p2_c = deck_to_args(decks[j])
            engine.setup_game(
                p1_f, p2_f,
                player1_deck_ids=p1_c, player1_leader_id=p1_l,
                player2_deck_ids=p2_c, player2_leader_id=p2_l,
            )

            validator = BoardValidator(engine)
            ctx = f"Matchup{i}-{j}"

            if not validator.validate_all(f"{ctx} setup"):
                total_errors += len(validator.errors)
            total_checks += 1

            await engine.start_game()

            if not validator.validate_all(f"{ctx} start"):
                total_errors += len(validator.errors)
            total_checks += 1

            for round_num in range(3):
                if not engine.game_state.is_playing:
                    break

                for turn in range(50):
                    player = engine.game_state.current_player
                    opponent = player.opponent

                    if player.passed and opponent.passed:
                        break
                    if player.passed:
                        engine.game_state.current_player = opponent
                        continue

                    if player.hand.cards and random.random() > 0.15:
                        card = random.choice(list(player.hand.cards))
                        await engine.play_card(player, card)
                    else:
                        await engine.pass_round(player)

                    engine.game_state.current_player = opponent

                    if not validator.validate_all(f"{ctx} R{round_num}T{turn}"):
                        total_errors += len(validator.errors)
                    total_checks += 1

                if not engine.game_state.player1.passed:
                    await engine.pass_round(engine.game_state.player1)
                if not engine.game_state.player2.passed:
                    await engine.pass_round(engine.game_state.player2)

                if not validator.validate_all(f"{ctx} R{round_num} pre-end"):
                    total_errors += len(validator.errors)
                total_checks += 1

                await engine.end_round()

                if not validator.validate_all(f"{ctx} R{round_num} post-end"):
                    total_errors += len(validator.errors)
                total_checks += 1

            matchup_count += 1

    print(f"\n📊 Board Validation Summary:")
    print(f"   Matchups: {matchup_count}")
    print(f"   Total checks: {total_checks}")
    print(f"   Total errors: {total_errors}")
    if total_errors == 0:
        print(f"   ✅ All board state validations passed!")
    else:
        print(f"   ❌ {total_errors} rule violations detected")
    assert total_errors == 0, f"{total_errors} board rule violations found"


# ============================================================================
# Runner
# ============================================================================

if __name__ == "__main__":
    print("⚔️  Board & Weather Tests:")
    test_row_score_basic()
    test_row_horn()
    test_row_weather()
    test_row_morale()
    test_row_bond()
    test_virtual_copy()
    asyncio.run(test_weather_zone())
    print("  All unit tests passed!\n")

    print("🔍 Board State Rule Validation Tests:")
    asyncio.run(test_board_validation_during_game())
