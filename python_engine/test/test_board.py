"""战场行与天气系统测试"""

import sys, os, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from python_engine.logger import setup_logger  # noqa: F401 - 初始化日志
from python_engine import (
    CardDefinition, CardInstance, Faction, RowType, AbilityType,
    BoardRow, RowEffects, WeatherZone, Player, GameState, Board,
)


def _make_card(name, strength, abilities=(), row=RowType.CLOSE, hero=False):
    abs_tuple = (AbilityType.HERO,) + tuple(abilities) if hero else tuple(abilities)
    d = CardDefinition(id=hash(name) % 10000, name=name, faction=Faction.NEUTRAL,
                       row=row, base_strength=strength, abilities=abs_tuple)
    return CardInstance(definition=d)


def test_row_score_basic():
    row = BoardRow(RowType.CLOSE)
    c1 = _make_card("A", 5)
    c2 = _make_card("B", 3)
    row.add_card(c1)
    row.update_state(c1, True)
    row.add_card(c2)
    row.update_state(c2, True)
    assert row.calculate_score() == 8
    print("  ✅ Basic row score")


def test_row_horn():
    row = BoardRow(RowType.CLOSE)
    c1 = _make_card("A", 5)
    row.add_card(c1)
    row.update_state(c1, True)
    assert row.calculate_score() == 5
    row.effects.horn = 1
    assert row.calculate_score() == 10
    print("  ✅ Horn effect")


def test_row_weather():
    row = BoardRow(RowType.CLOSE)
    c1 = _make_card("A", 10)
    c2 = _make_card("Hero", 10, hero=True)
    row.add_card(c1)
    row.update_state(c1, True)
    row.add_card(c2)
    row.update_state(c2, True)
    row.effects.weather = True
    score = row.calculate_score()
    # Non-hero reduced to 1, hero stays 10
    assert score == 11, f"Expected 11, got {score}"
    print("  ✅ Weather effect")


def test_row_morale():
    row = BoardRow(RowType.CLOSE)
    c1 = _make_card("Morale", 4, abilities=(AbilityType.MORALE,))
    c2 = _make_card("Unit", 3)
    row.add_card(c1)
    row.update_state(c1, True)
    row.add_card(c2)
    row.update_state(c2, True)
    # Morale adds +1 to others, morale card itself doesn't get its own bonus
    score = row.calculate_score()
    assert score == 4 + (3 + 1) == 8, f"Expected 8, got {score}"
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
    # bond count = 2, so both get doubled
    score = row.calculate_score()
    assert score == 8 + 8 == 16, f"Expected 16, got {score}"
    print("  ✅ Bond effect")


def test_virtual_copy():
    row = BoardRow(RowType.CLOSE)
    c1 = _make_card("A", 5)
    row.add_card(c1)
    row.update_state(c1, True)
    row.effects.horn = 1
    virtual = row.get_virtual_copy()
    assert virtual.effects.horn == 1
    assert len(virtual.cards) == 1
    assert virtual.cards[0] is not c1
    print("  ✅ Virtual copy")


async def test_weather_zone():
    wz = WeatherZone()
    p1 = Player("P1", Faction.NORTHERN_REALMS)
    p2 = Player("P2", Faction.NILFGAARD)
    gs = GameState(p1, p2)
    board = Board(gs)

    frost_def = CardDefinition(id=4, name="Biting Frost", faction=Faction.WEATHER,
                               row=RowType.WEATHER, base_strength=0,
                               abilities=(AbilityType.FROST,))
    frost = CardInstance(definition=frost_def)
    is_dup = wz.add_weather_card(frost, board)
    assert not is_dup
    assert wz.type_counts["frost"] == 1
    print("  ✅ WeatherZone")


if __name__ == "__main__":
    print("⚔️  Board & Weather Tests:")
    test_row_score_basic()
    test_row_horn()
    test_row_weather()
    test_row_morale()
    test_row_bond()
    test_virtual_copy()
    asyncio.run(test_weather_zone())
    print("  All passed!\n")
