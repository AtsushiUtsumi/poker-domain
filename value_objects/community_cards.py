from collections import Counter
from itertools import combinations

from poker_domain.value_objects.card import Card, Rank, Suit
from poker_domain.value_objects.hand import Hand, HandRank
from poker_domain.value_objects.hole_cards import HoleCards


class CommunityCards(tuple[Card, ...]):
    """ボード(コミュニティカード)。tuple[Card, ...] のサブクラスで、挙動は tuple と完全互換"""

    __slots__ = ()

    def evaluate(self, hole_cards: HoleCards) -> Hand:
        """手札と合わせた現状の役を返す (合計5枚未満の場合は評価不可)"""
        from poker_domain.hand_evaluator import HandEvaluator

        combined = tuple(self) + tuple(hole_cards)
        if len(combined) < 5:
            raise ValueError("役を判定するには合計5枚以上のカードが必要です")
        return HandEvaluator.evaluate(combined)

    def river_probabilities(self, hole_cards: HoleCards) -> dict[HandRank, float]:
        """
        リバーまでに残りのカードを全数列挙し、最終的な役 (HandRank) ごとの成立確率を返す。
        コミュニティカードが0枚 (プリフロップ) の場合は計算不可のため ValueError を送出する。
        """
        from poker_domain.hand_evaluator import HandEvaluator

        if len(self) == 0:
            raise ValueError("river_probabilities はコミュニティカードが1枚以上の場合のみ計算できます")

        known = set(self) | set(hole_cards)
        remaining = tuple(
            Card(suit=suit, rank=rank)
            for suit in Suit
            for rank in Rank
            if Card(suit=suit, rank=rank) not in known
        )

        cards_to_come = 5 - len(self)
        hole = tuple(hole_cards)
        board = tuple(self)

        counts: Counter[HandRank] = Counter()
        total = 0
        for draw in combinations(remaining, cards_to_come):
            hand = HandEvaluator.evaluate(board + draw + hole)
            counts[hand.rank] += 1
            total += 1

        return {rank: counts.get(rank, 0) / total for rank in HandRank}
