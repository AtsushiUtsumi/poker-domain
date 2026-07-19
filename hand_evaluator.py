from itertools import combinations
from collections import Counter

from poker_domain.value_objects.card import Card, Rank, Suit
from poker_domain.value_objects.community_cards import CommunityCards
from poker_domain.value_objects.hand import Hand, HandRank
from poker_domain.value_objects.hole_cards import HoleCards


class HandEvaluator:
    """7枚のカードから最も強い5枚の手を評価する"""

    @staticmethod
    def evaluate(cards: tuple[Card, ...]) -> Hand:
        """7枚(ホール2枚 + コミュニティ5枚)から最強の手を返す"""
        if len(cards) < 5:
            raise ValueError("役を判定するには5枚以上のカードが必要です")
        best: Hand | None = None
        for combo in combinations(cards, 5):
            hand = HandEvaluator._evaluate_five(tuple(combo))
            if best is None or HandEvaluator.compare(hand, best) > 0:
                best = hand
        assert best is not None
        return best

    @staticmethod
    def evaluate_hand(hole_cards: HoleCards, community_cards: CommunityCards) -> Hand:
        """手札とコミュニティカードを合わせた現状の役を返す (合計5枚未満の場合は評価不可)"""
        return HandEvaluator.evaluate(tuple(hole_cards) + tuple(community_cards))

    @staticmethod
    def river_probabilities(hole_cards: HoleCards, community_cards: CommunityCards) -> dict[HandRank, float]:
        """
        リバーまでに残りのカードを全数列挙し、最終的な役 (HandRank) ごとの成立確率を返す。
        コミュニティカードが0枚 (プリフロップ) の場合は計算不可のため ValueError を送出する。
        """
        if len(community_cards) == 0:
            raise ValueError("river_probabilities はコミュニティカードが1枚以上の場合のみ計算できます")

        known = set(community_cards) | set(hole_cards)
        remaining = tuple(
            Card(suit=suit, rank=rank)
            for suit in Suit
            for rank in Rank
            if Card(suit=suit, rank=rank) not in known
        )

        cards_to_come = 5 - len(community_cards)
        hole = tuple(hole_cards)
        board = tuple(community_cards)

        counts: Counter[HandRank] = Counter()
        total = 0
        for draw in combinations(remaining, cards_to_come):
            # 確率分布の集計には役カテゴリのみ必要なため、タイブレーカーまで計算する
            # evaluate() ではなく classify_category() で高速に判定する
            category = HandEvaluator.classify_category(board + draw + hole)
            counts[category] += 1
            total += 1

        return {rank: counts.get(rank, 0) / total for rank in HandRank}

    @staticmethod
    def classify_category(cards: tuple[Card, ...]) -> HandRank:
        """
        5枚以上のカードから、最も強い5枚の組み合わせの役カテゴリだけを判定する。
        evaluate() と違い、全 C(n,5) 組み合わせを列挙せずタイブレーカーも算出しないため、
        確率分布計算のように大量呼び出しが必要で役カテゴリのみあれば足りる用途に向く。
        """
        if len(cards) < 5:
            raise ValueError("役を判定するには5枚以上のカードが必要です")

        ranks = [c.rank.value for c in cards]
        suits = [c.suit for c in cards]

        suit_counts = Counter(suits)
        flush_suit = next((s for s, cnt in suit_counts.items() if cnt >= 5), None)

        if flush_suit is not None:
            flush_ranks = sorted({r for r, s in zip(ranks, suits) if s == flush_suit}, reverse=True)
            sf_high = HandEvaluator._best_straight_high(flush_ranks)
            if sf_high is not None:
                return HandRank.ROYAL_FLUSH if sf_high == 14 else HandRank.STRAIGHT_FLUSH

        rank_counts = Counter(ranks)
        by_count = sorted(rank_counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
        pattern = tuple(c for _, c in by_count)

        if pattern[0] == 4:
            return HandRank.FOUR_OF_A_KIND

        if pattern[0] == 3 and len(pattern) > 1 and pattern[1] >= 2:
            return HandRank.FULL_HOUSE

        if flush_suit is not None:
            return HandRank.FLUSH

        straight_high = HandEvaluator._best_straight_high(sorted(set(ranks), reverse=True))
        if straight_high is not None:
            return HandRank.STRAIGHT

        if pattern[0] == 3:
            return HandRank.THREE_OF_A_KIND

        if pattern[0] == 2 and pattern.count(2) >= 2:
            return HandRank.TWO_PAIR

        if pattern[0] == 2:
            return HandRank.ONE_PAIR

        return HandRank.HIGH_CARD

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
    def _best_straight_high(desc_unique_ranks: list[int]) -> int | None:
        """
        降順・重複なしのランク列(5枚超も可)から、最も高いストレートの最上位ランクを返す
        (無ければNone)。ホイール(A-2-3-4-5)はAを1として末尾に加えて判定する。
        """
        values = desc_unique_ranks
        if 14 in values and 1 not in values:
            values = values + [1]
        for i in range(len(values) - 4):
            if values[i] - values[i + 4] == 4:
                return values[i]
        return None

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
