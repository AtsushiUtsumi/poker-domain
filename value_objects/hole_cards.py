import math

from poker_domain.value_objects.card import Card, Rank

_HIGH_CARD_SCORES: dict[Rank, float] = {
    Rank.ACE: 10,
    Rank.KING: 8,
    Rank.QUEEN: 7,
    Rank.JACK: 6,
}

_GAP_PENALTIES: dict[int, int] = {0: 0, 1: 1, 2: 2, 3: 4}


class HoleCards(tuple[Card, ...]):
    """プレイヤーの手札(ホールカード)。tuple[Card, ...] のサブクラスで、挙動は tuple と完全互換"""

    __slots__ = ()

    def power_number(self) -> int:
        """
        チェン・フォーミュラによるプリフロップの手札の強さを返す (AA=20が最高、72oが最低)。
        2枚の手札に対してのみ計算できる。
        """
        if len(self) != 2:
            raise ValueError("power_number は2枚の手札に対してのみ計算できます")

        first, second = self
        high, low = sorted((first.rank, second.rank), key=lambda r: r.value, reverse=True)
        is_pair = high == low

        score = _HIGH_CARD_SCORES.get(high, high.value / 2)

        if is_pair:
            score = max(score * 2, 5)
        else:
            gap = high.value - low.value - 1
            score -= _GAP_PENALTIES.get(gap, 5)
            if gap <= 1 and high.value < Rank.QUEEN.value:
                score += 1
            if first.suit == second.suit:
                score += 2

        return math.ceil(score)
