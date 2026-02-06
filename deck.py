import random

from poker_domain.value_objects.card import Card, Suit, Rank
from poker_domain.exceptions import DeckEmptyError


class Deck:
    """52枚のカードデック"""

    def __init__(self) -> None:
        self._cards: list[Card] = [
            Card(suit=suit, rank=rank)
            for suit in Suit
            for rank in Rank
        ]

    def shuffle(self) -> None:
        random.shuffle(self._cards)

    def deal(self, count: int = 1) -> tuple[Card, ...]:
        if len(self._cards) < count:
            raise DeckEmptyError(f"デックに {count} 枚あませんが、残り {len(self._cards)} 枚です")
        dealt = tuple(self._cards[:count])
        self._cards = self._cards[count:]
        return dealt

    @property
    def remaining(self) -> int:
        return len(self._cards)
