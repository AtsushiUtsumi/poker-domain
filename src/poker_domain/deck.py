import random

from poker_domain.exceptions import DeckEmptyError
from poker_domain.value_objects.card import Card, Rank, Suit


class Deck:
    """52枚のカードデック"""

    def __init__(self, rng: random.Random | None = None) -> None:
        # rng 未指定時は random モジュールをそのまま使う (従来通り random.shuffle を差し替えて
        # テストできる)。random.Random インスタンスを渡せばデッキごとに独立した乱数系列にできる
        self._rng = rng if rng is not None else random
        self._cards: list[Card] = [
            Card(suit=suit, rank=rank)
            for suit in Suit
            for rank in Rank
        ]

    def shuffle(self) -> None:
        self._rng.shuffle(self._cards)

    def deal(self, count: int = 1) -> tuple[Card, ...]:
        if len(self._cards) < count:
            raise DeckEmptyError(f"デックに {count} 枚あませんが、残り {len(self._cards)} 枚です")
        dealt = tuple(self._cards[:count])
        self._cards = self._cards[count:]
        return dealt

    @property
    def remaining(self) -> int:
        return len(self._cards)
