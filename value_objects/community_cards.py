from poker_domain.value_objects.card import Card
from poker_domain.value_objects.hand import Hand
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
