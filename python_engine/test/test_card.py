"""卡牌、容器与工厂测试"""

import asyncio
from conftest import (
    make_card, make_card_def, create_game_state,
    CardDefinition, CardInstance, Faction, RowType, AbilityType,
    Hand, Deck, Graveyard, CardContainer,
)
from python_engine.factory import create_card_from_dict
from python_engine.abilities import execute_muster


# ============================================================================
# CardDefinition & CardInstance
# ============================================================================

def test_card_definition():
    d = CardDefinition(
        id=1, name="Test", faction=Faction.NEUTRAL,
        row=RowType.CLOSE, base_strength=5,
        abilities=(AbilityType.HERO,), max_count=1,
    )
    assert d.is_unit
    assert d.is_hero
    assert not d.is_special
    print("  ✅ CardDefinition")


def test_card_instance():
    d = CardDefinition(
        id=2, name="Spy", faction=Faction.NILFGAARD,
        row=RowType.CLOSE, base_strength=3,
        abilities=(AbilityType.SPY,),
    )
    c = CardInstance(definition=d)
    assert c.current_strength == 3
    assert c.has_ability(AbilityType.SPY)
    assert not c.has_ability(AbilityType.HERO)
    clone = c.clone()
    assert clone.current_strength == 3
    assert clone.definition is d
    print("  ✅ CardInstance")


# ============================================================================
# Container: Hand / Deck / Graveyard
# ============================================================================

def test_hand_deck_grave():
    d = CardDefinition(id=1, name="A", faction=Faction.NEUTRAL,
                       row=RowType.CLOSE, base_strength=1, abilities=())
    hand = Hand("h")
    deck = Deck("d")
    grave = Graveyard("g")

    cards = [CardInstance(definition=d) for _ in range(5)]
    for c in cards:
        deck.add_card(c)
    assert len(deck) == 5

    drawn = deck.draw(hand, 3)
    assert len(drawn) == 3
    assert len(hand) == 3
    assert len(deck) == 2

    randoms = hand.find_cards_random(lambda c: True, 2)
    assert len(randoms) == 2

    removed = hand.get_cards(lambda c: True)
    assert len(removed) == 3
    assert len(hand) == 0

    print("  ✅ Hand/Deck/Graveyard")


def test_container_find():
    d1 = CardDefinition(id=1, name="Hero", faction=Faction.NEUTRAL,
                        row=RowType.CLOSE, base_strength=10,
                        abilities=(AbilityType.HERO,))
    d2 = CardDefinition(id=2, name="Unit", faction=Faction.NEUTRAL,
                        row=RowType.RANGED, base_strength=3, abilities=())
    container = CardContainer("test")
    c1 = CardInstance(definition=d1)
    c2 = CardInstance(definition=d2)
    container.add_card(c1)
    container.add_card(c2)

    heroes = container.find_cards(lambda c: c.is_hero)
    assert len(heroes) == 1
    units = container.get_units()
    assert len(units) == 2
    found = container.find_card(lambda c: c.name == "Unit")
    assert found is c2
    print("  ✅ Container find methods")


# ============================================================================
# Factory: muster_name 解析
# ============================================================================

def test_factory_parses_muster_field():
    data = {
        "name": "Geralt of Rivia", "id": "7", "deck": "neutral",
        "row": "close", "strength": "15", "ability": "hero muster",
        "filename": "geralt", "count": "1", "muster": "Roach",
    }
    card_def = create_card_from_dict(data)
    assert card_def.muster_name == "Roach"
    print("  ✅ Factory parses muster field")


def test_factory_muster_defaults_empty():
    data = {
        "name": "Blue Stripes Commando", "id": "92", "deck": "realms",
        "row": "close", "strength": "4", "ability": "bond",
        "filename": "blue_stripes", "count": "3",
    }
    card_def = create_card_from_dict(data)
    assert card_def.muster_name == ""
    print("  ✅ Factory muster defaults to empty")


# ============================================================================
# Muster: 自定义名称匹配
# ============================================================================

async def test_muster_uses_custom_name():
    """Geralt (muster_name='Roach') 只召唤 Roach，不误召其他卡"""
    _, board, p1, _ = create_game_state()

    geralt = CardInstance(
        definition=make_card_def("Geralt of Rivia", 15,
                                 abilities=(AbilityType.HERO, AbilityType.MUSTER),
                                 muster_name="Roach"),
        holder=p1,
    )
    roach = CardInstance(definition=make_card_def("Roach", 3), holder=p1)
    other = CardInstance(definition=make_card_def("Other Horse", 2), holder=p1)
    p1.deck.add_card(roach)
    p1.deck.add_card(other)

    await execute_muster(geralt, board)

    remaining = [c.name for c in p1.deck.cards]
    assert "Roach" not in remaining, "Roach should have been summoned"
    assert "Other Horse" in remaining, "Other Horse should NOT be summoned"
    print("  ✅ Muster uses custom muster_name")


async def test_muster_fallback_to_card_name():
    """无 muster_name 时回退到 card.name 前缀匹配"""
    _, board, p1, _ = create_game_state()

    bond = CardInstance(
        definition=make_card_def("Blue Stripes Commando", 4,
                                 abilities=(AbilityType.MUSTER,)),
        holder=p1,
    )
    bond2 = CardInstance(
        definition=make_card_def("Blue Stripes Commando", 4,
                                 abilities=(AbilityType.BOND,)),
        holder=p1,
    )
    p1.deck.add_card(bond2)

    await execute_muster(bond, board)

    assert len(p1.deck.cards) == 0, "Blue Stripes should have been summoned"
    print("  ✅ Muster fallback to card.name")


# ============================================================================
# Runner
# ============================================================================

if __name__ == "__main__":
    print("🃏 Card, Container & Factory Tests:")
    test_card_definition()
    test_card_instance()
    test_hand_deck_grave()
    test_container_find()
    test_factory_parses_muster_field()
    test_factory_muster_defaults_empty()
    asyncio.run(test_muster_uses_custom_name())
    asyncio.run(test_muster_fallback_to_card_name())
    print("  All passed!\n")
