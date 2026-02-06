from itertools import combinations
from collections import Counter

from poker_domain.value_objects.card import Card, Rank
from poker_domain.value_objects.hand import Hand, HandRank


class HandEvaluator:
    """7枚のカードから最も強い5枚の手を評価する"""

    @staticmethod
    def evaluate(cards: tuple[Card, ...]) -> Hand:
        """7枚(ホール2枚 + コミュニティ5枚)から最強の手を返す"""
        best: Hand | None = None
        for combo in combinations(cards, 5):
            hand = HandEvaluator._evaluate_five(tuple(combo))
            if best is None or HandEvaluator.compare(hand, best) > 0:
                best = hand
        return best  # type: ignore

    @staticmethod
    def compare(hand_a: Hand, hand_b: Hand) -> int:
        """正: hand_a が強い / 負: hand_b が強い / 0: 同じ強さ"""
        if hand_a.rank != hand_b.rank:
            return hand_a.rank - hand_b.rank
        # 同ランク → tiebreakers で比較
        for a, b in zip(hand_a.tiebreakers, hand_b.tiebreakers):
            if a != b:
                return a - b
        return 0

    # ─── 内部 ───

    @staticmethod
    def _evaluate_five(cards: tuple[Card, ...]) -> Hand:
        ranks = sorted([c.rank.value for c in cards], reverse=True)
        suits = [c.suit for c in cards]

        is_flush = len(set(suits)) == 1
        is_straight, straight_high = HandEvaluator._check_straight(ranks)

        counts = Counter(ranks)
        # (出現回数, ランク) で降順ソート → パターン判定に使う
        by_count = sorted(counts.items(), key=lambda x: (x[1], x[0]), reverse=True)
        count_pattern = tuple(c for _, c in by_count)

        # ── ハンドランク判定 ──
        if is_flush and is_straight:
            if ranks == [14, 13, 12, 11, 10]:
                return Hand(cards=cards, rank=HandRank.ROYAL_FLUSH, tiebreakers=())
            return Hand(cards=cards, rank=HandRank.STRAIGHT_FLUSH, tiebreakers=(straight_high,))

        if count_pattern == (4, 1):
            quad_rank = by_count[0][0]
            kicker = by_count[1][0]
            return Hand(cards=cards, rank=HandRank.FOUR_OF_A_KIND, tiebreakers=(quad_rank, kicker))

        if count_pattern == (3, 2):
            trips_rank = by_count[0][0]
            pair_rank = by_count[1][0]
            return Hand(cards=cards, rank=HandRank.FULL_HOUSE, tiebreakers=(trips_rank, pair_rank))

        if is_flush:
            return Hand(cards=cards, rank=HandRank.FLUSH, tiebreakers=tuple(ranks))

        if is_straight:
            return Hand(cards=cards, rank=HandRank.STRAIGHT, tiebreakers=(straight_high,))

        if count_pattern == (3, 1, 1):
            trips_rank = by_count[0][0]
            kickers = sorted([r for r, c in by_count if c == 1], reverse=True)
            return Hand(cards=cards, rank=HandRank.THREE_OF_A_KIND, tiebreakers=(trips_rank, *kickers))

        if count_pattern == (2, 2, 1):
            pairs = sorted([r for r, c in by_count if c == 2], reverse=True)
            kicker = [r for r, c in by_count if c == 1][0]
            return Hand(cards=cards, rank=HandRank.TWO_PAIR, tiebreakers=(*pairs, kicker))

        if count_pattern == (2, 1, 1, 1):
            pair_rank = by_count[0][0]
            kickers = sorted([r for r, c in by_count if c == 1], reverse=True)
            return Hand(cards=cards, rank=HandRank.ONE_PAIR, tiebreakers=(pair_rank, *kickers))

        return Hand(cards=cards, rank=HandRank.HIGH_CARD, tiebreakers=tuple(ranks))

    @staticmethod
    def _check_straight(ranks: list[int]) -> tuple[bool, int]:
        """
        ストレートか判定。
        戻り値: (はストレートか, ストレートの最上位カード)
        ホイール (A-2-3-4-5) の場合は最上位カードは 5 とする。
        """
        # 通常のストレート
        if ranks[0] - ranks[4] == 4 and len(set(ranks)) == 5:
            return True, ranks[0]
        # ホイール: A-2-3-4-5
        if set(ranks) == {14, 2, 3, 4, 5}:
            return True, 5
        return False, 0
