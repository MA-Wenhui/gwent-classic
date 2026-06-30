"""Board 状态规则验证测试 - 每步操作后验证 board 是否符合游戏规则"""

import sys, os, asyncio, json, random
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from python_engine.logger import setup_logger  # noqa: F401
from python_engine import GameEngine, Faction, AbilityType, RowType


class BoardValidator:
    """Board 状态规则验证器"""

    def __init__(self, engine: GameEngine):
        self.engine = engine
        self.errors = []

    def validate_all(self, context: str = "") -> bool:
        """执行所有规则检查，返回是否全部通过"""
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

        if self.errors:
            prefix = f"[{context}] " if context else ""
            for err in self.errors:
                print(f"  ❌ {prefix}{err}")
            return False
        return True

    def _check_special_card_limit(self):
        """规则：每行最多1个特殊卡（Horn/Mardroeme），且 special_card 与 cards 列表互斥
        JS isSpecial() = name === "Commander's Horn" || name === "Mardroeme"
        Decoy 虽 is_special=True 但替换目标后留在 cards 列表中是正确行为，需排除"""
        special_names = {"Commander's Horn", "Mardroeme"}
        for key, row in self.engine.board.rows.items():
            # 只有 Commander's Horn 和 Mardroeme 不应出现在 cards 列表中
            special_in_cards = [c for c in row.cards if c.name in special_names]
            if len(special_in_cards) > 0:
                self.errors.append(
                    f"Row {row.name} has {len(special_in_cards)} special card(s) in cards list "
                    f"(should be in special_card slot): {[c.name for c in special_in_cards]}"
                )
            # 如果 special_card 存在，验证它确实是 Commander's Horn 或 Mardroeme
            if row.special_card is not None and row.special_card.name not in special_names:
                self.errors.append(
                    f"Row {row.name} special_card={row.special_card.name} is not Commander's Horn/Mardroeme"
                )

    def _check_hero_immunity(self):
        """规则：Hero 卡 current_strength 必须等于 base_strength"""
        for key, row in self.engine.board.rows.items():
            for card in row.cards:
                if card.is_hero and card.current_strength != card.definition.base_strength:
                    self.errors.append(
                        f"Hero {card.name} in {row.name}: strength={card.current_strength}, "
                        f"expected base={card.definition.base_strength}"
                    )

    def _check_weather_effect(self):
        """规则：天气效果正确应用，用引擎 calculate_card_score 精确验证"""
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
                        f"Weather row {row.name}: {card.name} strength={card.current_strength}, "
                        f"expected={expected} (hero={card.is_hero}, half={row.effects.half_weather})"
                    )

    def _check_spy_placement(self):
        """规则：Spy 卡必须在对手的行上"""
        for key, row in self.engine.board.rows.items():
            for card in row.cards:
                if card.has_ability(AbilityType.SPY):
                    if card.holder is None:
                        continue
                    # spy 的 holder 应该是对手，所以行 owner 应该是 holder
                    if row.owner is not None and row.owner != card.holder:
                        self.errors.append(
                            f"Spy {card.name} in {row.name}: holder={card.holder.name}, "
                            f"row_owner={row.owner.name}"
                        )

    def _check_bond_multiplier(self):
        """规则：bond 效果正确应用，用引擎 calculate_card_score 精确验证"""
        for key, row in self.engine.board.rows.items():
            has_any_bond = any(v > 1 for v in row.effects.bond.values())
            if not has_any_bond:
                continue
            double_spy = self.engine.game_state.double_spy_power if self.engine.game_state else False
            for card in row.cards:
                if card.name == "Decoy":
                    continue
                expected = row.calculate_card_score(card, double_spy)
                if card.current_strength != expected:
                    self.errors.append(
                        f"Bond row {row.name}: {card.name} strength={card.current_strength}, "
                        f"expected={expected} (bond_count={row.effects.bond.get(card.name, 0)})"
                    )

    def _check_horn_multiplier(self):
        """规则：horn 效果正确应用，用引擎 calculate_card_score 精确验证"""
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
                        f"Horn row {row.name}: {card.name} strength={card.current_strength}, "
                        f"expected={expected}"
                    )

    def _check_row_score_consistency(self):
        """规则：行总分 = 所有卡牌 current_strength 之和"""
        for key, row in self.engine.board.rows.items():
            calculated = sum(c.current_strength for c in row.cards)
            if row.total_score != calculated:
                self.errors.append(
                    f"Row {row.name}: total_score={row.total_score}, "
                    f"sum_of_cards={calculated}"
                )

    def _check_decoy_zero_power(self):
        """规则：Decoy 战力必须为 0"""
        for key, row in self.engine.board.rows.items():
            for card in row.cards:
                if card.name == "Decoy" and card.current_strength != 0:
                    self.errors.append(
                        f"Decoy in {row.name}: strength={card.current_strength}, expected 0"
                    )

    def _check_card_holder_consistency(self):
        """规则：行上的卡牌 holder 应与行 owner 一致（spy 除外）"""
        for key, row in self.engine.board.rows.items():
            if row.owner is None:
                continue
            for card in row.cards:
                if card.has_ability(AbilityType.SPY):
                    continue
                if card.holder is not None and card.holder != row.owner:
                    self.errors.append(
                        f"Card {card.name} in {row.name}: holder={card.holder.name}, "
                        f"row_owner={row.owner.name}"
                    )

    def _check_morale_bonus(self):
        """规则：morale 效果正确应用（同行所有单位 +1，morale 卡自身不加）
        用引擎 calculate_card_score 精确验证"""
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
                        f"Morale row {row.name}: {card.name} strength={card.current_strength}, "
                        f"expected={expected} (morale={row.effects.morale}, is_morale={card.has_ability(AbilityType.MORALE)})"
                    )

    def _check_mardroeme_effect(self):
        """规则：Mardroeme 使同行非英雄单位战力减半（向下取整），hero 免疫
        用引擎 calculate_card_score 精确验证"""
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
                        f"Mardroeme row {row.name}: {card.name} strength={card.current_strength}, "
                        f"expected={expected} (mardroeme={row.effects.mardroeme}, hero={card.is_hero})"
                    )

    def _check_effects_consistency(self):
        """规则：effects 标记与实际卡牌/特殊卡状态一致
        - horn > 0 时必须有 Horn 卡或 Dandelion 在场上
        - mardroeme > 0 时必须有 Mardroeme 在 special_card 槽位
        - morale > 0 时必须有 Morale/Vildkaarl Morale 卡在场上
        - bond 中每个 key 对应的卡牌数量应 >= bond count
        """
        for key, row in self.engine.board.rows.items():
            # horn 一致性
            horn_cards = [c for c in row.cards if c.has_ability(AbilityType.HORN)]
            horn_special = (row.special_card is not None and
                           row.special_card.name == "Commander's Horn")
            actual_horn_sources = len(horn_cards) + (1 if horn_special else 0)
            if row.effects.horn > 0 and actual_horn_sources == 0:
                self.errors.append(
                    f"Row {row.name}: effects.horn={row.effects.horn} but no horn source on field"
                )

            # mardroeme 一致性
            if row.effects.mardroeme > 0:
                has_mardroeme = (row.special_card is not None and
                                row.special_card.name == "Mardroeme")
                if not has_mardroeme:
                    self.errors.append(
                        f"Row {row.name}: effects.mardroeme={row.effects.mardroeme} "
                        f"but no Mardroeme in special_card slot"
                    )

            # morale 一致性
            morale_cards = [c for c in row.cards
                          if c.has_ability(AbilityType.MORALE) or
                          c.has_ability(AbilityType.VILDKAARL_MORALE)]
            if row.effects.morale > 0 and len(morale_cards) == 0:
                self.errors.append(
                    f"Row {row.name}: effects.morale={row.effects.morale} but no morale source on field"
                )

            # bond 一致性
            for bond_name, bond_count in row.effects.bond.items():
                if bond_count > 1:
                    matching = [c for c in row.cards if c.name == bond_name]
                    if len(matching) < bond_count:
                        self.errors.append(
                            f"Row {row.name}: bond[{bond_name}]={bond_count} "
                            f"but only {len(matching)} matching cards on field"
                        )


async def test_board_validation_during_game():
    """完整对局中每步操作后验证 board 状态"""
    with open("python_engine/decks.json") as f:
        decks = json.load(f)

    faction_map = {
        "realms": Faction.NORTHERN_REALMS,
        "nilfgaard": Faction.NILFGAARD,
        "monsters": Faction.MONSTERS,
        "scoiatael": Faction.SCOIATAEL,
        "skellige": Faction.SKELLIGE,
    }

    total_checks = 0
    total_errors = 0

    # 所有预设牌组两两对战
    matchup_count = 0
    for i in range(len(decks)):
        for j in range(i + 1, len(decks)):
            p1_data = decks[i]
            p2_data = decks[j]

            engine = GameEngine("python_engine/cards.json")
            p1_f = faction_map[p1_data["faction"]]
            p2_f = faction_map[p2_data["faction"]]
            p1_cards = [tuple(c) for c in p1_data["cards"]]
            p2_cards = [tuple(c) for c in p2_data["cards"]]

            engine.setup_game(
                p1_f, p2_f,
                player1_deck_ids=p1_cards, player1_leader_id=p1_data.get("leader"),
                player2_deck_ids=p2_cards, player2_leader_id=p2_data.get("leader"),
            )

            validator = BoardValidator(engine)
            ctx = f"Matchup{i}-{j}"

            # 验证 setup 后
            if not validator.validate_all(f"{ctx} setup"):
                total_errors += len(validator.errors)
            total_checks += 1

            await engine.start_game()

            # 验证 start_game 后
            if not validator.validate_all(f"{ctx} start"):
                total_errors += len(validator.errors)
            total_checks += 1

            # 模拟完整ROUND轮对战，每轮最多STEPS步
            ROUND = 3
            STEPS = 50
            for round_num in range(ROUND):
                if not engine.game_state.is_playing:
                    break

                for turn in range(STEPS):
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

                    # 每步操作后验证
                    if not validator.validate_all(f"{ctx} R{round_num}T{turn}"):
                        total_errors += len(validator.errors)
                    total_checks += 1

                # 确保双方都 pass
                if not engine.game_state.player1.passed:
                    await engine.pass_round(engine.game_state.player1)
                if not engine.game_state.player2.passed:
                    await engine.pass_round(engine.game_state.player2)

                # 结束轮次前验证
                if not validator.validate_all(f"{ctx} R{round_num} pre-end"):
                    total_errors += len(validator.errors)
                total_checks += 1

                await engine.end_round()

                # 轮次结束后验证
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


if __name__ == "__main__":
    print("🔍 Board State Rule Validation Tests:")
    asyncio.run(test_board_validation_during_game())
