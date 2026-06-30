"""卡牌容器：Hand / Deck / Graveyard"""

from __future__ import annotations
import logging
import random
from typing import List, Optional, Callable

from .card import CardInstance

log = logging.getLogger("gwent.container")


class CardContainer:
    """通用卡牌容器基类"""

    def __init__(self, name: str = ""):
        self.name = name
        self._cards: List[CardInstance] = []

    @property
    def cards(self) -> List[CardInstance]:
        return self._cards

    def __len__(self) -> int:
        return len(self._cards)

    def __iter__(self):
        return iter(self._cards)

    def add_card(self, card: CardInstance, index: Optional[int] = None) -> None:
        if index is not None:
            index = max(0, min(index, len(self._cards)))
            self._cards.insert(index, card)
        else:
            self._cards.append(card)
        log.debug(f"  📥 [{self.name}] +{card.name} (size={len(self._cards)})")

    def remove_card(self, card_or_index) -> Optional[CardInstance]:
        if isinstance(card_or_index, int):
            if 0 <= card_or_index < len(self._cards):
                removed = self._cards.pop(card_or_index)
                log.debug(f"  📤 [{self.name}] -{removed.name} (size={len(self._cards)})")
                return removed
            return None
        try:
            self._cards.remove(card_or_index)
            log.debug(f"  📤 [{self.name}] -{card_or_index.name} (size={len(self._cards)})")
            return card_or_index
        except ValueError:
            log.warning(f"  ⚠️  [{self.name}] remove failed: card not found")
            return None

    def find_cards(self, predicate: Callable[[CardInstance], bool]) -> List[CardInstance]:
        return [c for c in self._cards if predicate(c)]

    def find_card(self, predicate: Callable[[CardInstance], bool]) -> Optional[CardInstance]:
        for card in self._cards:
            if predicate(card):
                return card
        return None

    def find_cards_random(self, predicate: Callable[[CardInstance], bool], count: int = 1) -> List[CardInstance]:
        """随机选取最多 count 张满足条件的卡牌（不修改容器）"""
        valid = [c for c in self._cards if predicate(c)]
        if not valid:
            return []
        if count <= 1:
            return [valid[random.randint(0, len(valid) - 1)]]
        pool = list(valid)
        result = []
        for _ in range(min(count, len(pool))):
            idx = random.randint(0, len(pool) - 1)
            result.append(pool.pop(idx))
        return result

    def get_cards(self, predicate: Callable[[CardInstance], bool]) -> List[CardInstance]:
        """移除并返回所有满足条件的卡牌"""
        indices = [i for i, c in enumerate(self._cards) if predicate(c)]
        result = []
        for idx in reversed(indices):
            result.append(self._cards.pop(idx))
        result.reverse()
        return result

    def get_card(self, predicate: Callable[[CardInstance], bool]) -> Optional[CardInstance]:
        """移除并返回第一张满足条件的卡牌（从末尾开始搜索）"""
        for i in range(len(self._cards) - 1, -1, -1):
            if predicate(self._cards[i]):
                return self._cards.pop(i)
        return None

    def get_units(self) -> List[CardInstance]:
        return self.find_cards(lambda c: c.is_unit)

    def clear(self) -> None:
        self._cards.clear()


class Hand(CardContainer):
    """手牌"""
    pass


class Deck(CardContainer):
    """牌堆"""

    def draw(self, target: 'Hand', count: int = 1) -> List[CardInstance]:
        drawn = []
        actual = min(count, len(self._cards))
        for _ in range(actual):
            card = self._cards.pop(0)
            target.add_card(card)
            drawn.append(card)
        if drawn:
            names = ", ".join(c.name for c in drawn)
            log.info(f"  🃏 Draw {len(drawn)} card(s): {names}")
        return drawn

    def shuffle(self) -> None:
        random.shuffle(self._cards)
        log.debug(f"  🔀 [{self.name}] shuffled ({len(self._cards)} cards)")

    def swap(self, hand: 'Hand', card: CardInstance) -> bool:
        if not self._cards or card not in hand.cards:
            return False
        hand.remove_card(card)
        top_card = self._cards.pop(0)
        hand.add_card(top_card)
        self._cards.append(card)
        log.info(f"  🔄 Swap: {card.name} ↔ {top_card.name}")
        return True


class Graveyard(CardContainer):
    """墓地"""
    pass
