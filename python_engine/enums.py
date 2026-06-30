"""枚举类型定义"""

from enum import Enum


class Faction(Enum):
    """阵营枚举"""
    NORTHERN_REALMS = "realms"
    NILFGAARD = "nilfgaard"
    MONSTERS = "monsters"
    SCOIATAEL = "scoiatael"
    SKELLIGE = "skellige"
    NEUTRAL = "neutral"
    WEATHER = "weather"
    SPECIAL = "special"


class RowType(Enum):
    """战场行类型"""
    CLOSE = "close"
    RANGED = "ranged"
    SIEGE = "siege"
    AGILE = "agile"
    LEADER = "leader"
    WEATHER = "weather"
    SPECIAL = "special"
    GRAVE = "grave"
    HAND = "hand"
    DECK = "deck"


class AbilityType(Enum):
    """卡牌能力类型"""
    HERO = "hero"
    MUSTER = "muster"
    SPY = "spy"
    MEDIC = "medic"
    MORALE = "morale"
    BOND = "bond"
    SCORCH = "scorch"
    SCORCH_C = "scorch_c"
    SCORCH_R = "scorch_r"
    SCORCH_S = "scorch_s"
    HORN = "horn"
    BERSERKER = "berserker"
    AVENGER = "avenger"
    AVENGER_KAMBI = "avenger_kambi"
    MARDROEME = "mardroeme"
    DECOY = "decoy"
    CLEAR_WEATHER = "clear_weather"
    VILDKAARL_MORALE = "vildkarrl morale"
    VILDKAARL_BOND = "vildkarrl bond"
    FRANCESCA_DAISY = "francesca_daisy"
    KING_BRAN = "king_bran"
    FROST = "frost"
    RAIN = "rain"
    FOG = "fog"
    STORM = "storm"
