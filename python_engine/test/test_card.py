"""卡牌与容器基础测试"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from python_engine.logger import setup_logger  # noqa: F401 - 初始化日志
from python_engine import (
    CardDefinition, CardInstance, Faction, RowType, AbilityType,
    Hand, Deck, Graveyard, CardContainer,
)


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

    # find_cards_random
    randoms = hand.find_cards_random(lambda c: True, 2)
    assert len(randoms) == 2

    # get_cards (remove)
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


if __name__ == "__main__":
    print("🃏 Card & Container Tests:")
    test_card_definition()
    test_card_instance()
    test_hand_deck_grave()
    test_container_find()
    print("  All passed!\n")
