"""卡牌定义与实例"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Any, TYPE_CHECKING

from .enums import AbilityType, Faction, RowType

log = logging.getLogger("gwent.card")

if TYPE_CHECKING:
    from .board import BoardRow


@dataclass(frozen=True)
class CardDefinition:
    """卡牌定义模板（不可变）"""
    id: int
    name: str
    faction: Faction
    row: RowType
    base_strength: int
    abilities: tuple[AbilityType, ...]
    max_count: int = 1
    filename: str = ""

    @property
    def is_unit(self) -> bool:
        return self.row in (RowType.CLOSE, RowType.RANGED, RowType.SIEGE, RowType.AGILE)

    @property
    def is_hero(self) -> bool:
        return AbilityType.HERO in self.abilities

    @property
    def is_special(self) -> bool:
        # JS isSpecial() = name === "Commander's Horn" || name === "Mardroeme"
        # Python 等价判断：非单位、非天气、非领袖
        return not self.is_unit and self.faction != Faction.WEATHER and self.row != RowType.LEADER


@dataclass
class CardInstance:
    """卡牌运行时实例"""
    definition: CardDefinition
    holder: Optional['Player'] = None  # type: ignore[name-defined]  # noqa: F821
    current_row: Optional[RowType] = None
    current_strength: int = 0
    is_face_down: bool = False
    no_remove: bool = False
    is_transformed: bool = False

    placed_callbacks: List[Callable[['CardInstance', 'BoardRow'], Any]] = field(default_factory=list)
    removed_callbacks: List[Callable[['CardInstance'], Any]] = field(default_factory=list)

    def __post_init__(self):
        if self.current_strength == 0:
            self.current_strength = self.definition.base_strength

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def abilities(self) -> tuple[AbilityType, ...]:
        return self.definition.abilities

    @property
    def is_unit(self) -> bool:
        return self.definition.is_unit

    @property
    def is_hero(self) -> bool:
        return self.definition.is_hero

    def has_ability(self, ability: AbilityType) -> bool:
        return ability in self.definition.abilities

    def set_power(self, power: int) -> None:
        old = self.current_strength
        self.current_strength = power
        if old != power:
            log.debug(f"  ⚡ {self.name} strength: {old} → {power}")

    def reset_power(self) -> None:
        self.current_strength = self.definition.base_strength
        log.debug(f"  ↩️  {self.name} strength reset to {self.current_strength}")

    def clone(self) -> 'CardInstance':
        return CardInstance(
            definition=self.definition,
            holder=self.holder,
            current_row=self.current_row,
            current_strength=self.current_strength,
            is_face_down=self.is_face_down,
            no_remove=self.no_remove,
            is_transformed=self.is_transformed,
        )
