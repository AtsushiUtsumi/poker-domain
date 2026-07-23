from dataclasses import dataclass
from enum import IntEnum

from poker_domain.value_objects.card import Card


class HandRank(IntEnum):
    HIGH_CARD = 0
    ONE_PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8
    ROYAL_FLUSH = 9


@dataclass(frozen=True)
class Hand:
    cards: tuple[Card, ...]  # 5枚
    rank: HandRank
    tiebreakers: tuple[int, ...]  # 同ランク時の比較順位カード (高い順)
