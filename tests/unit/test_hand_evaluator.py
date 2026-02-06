from poker_domain.hand_evaluator import HandEvaluator
from poker_domain.value_objects.card import Card, Suit, Rank
from poker_domain.value_objects.hand import HandRank

def create_cards(card_strs):
    """
    "Ah", "Kd", "10s", "2c" のような文字列からCardオブジェクトのタプルを生成するヘルパー
    """
    suit_map = {
        "h": Suit.HEARTS, "d": Suit.DIAMONDS, "s": Suit.SPADES, "c": Suit.CLUBS
    }
    rank_map = {
        "2": Rank.TWO, "3": Rank.THREE, "4": Rank.FOUR, "5": Rank.FIVE, 
        "6": Rank.SIX, "7": Rank.SEVEN, "8": Rank.EIGHT, "9": Rank.NINE, 
        "10": Rank.TEN, "J": Rank.JACK, "Q": Rank.QUEEN, "K": Rank.KING, "A": Rank.ACE
    }
    
    cards = []
    for s in card_strs:
        rank_str = s[:-1]
        suit_str = s[-1].lower()
        cards.append(Card(suit_map[suit_str], rank_map[rank_str]))
    return tuple(cards)

def test_royal_flush():
    cards = create_cards(["Ah", "Kh", "Qh", "Jh", "10h", "2d", "3c"])
    hand = HandEvaluator.evaluate(cards)
    assert hand.rank == HandRank.ROYAL_FLUSH

def test_straight_flush():
    cards = create_cards(["9h", "Kh", "Qh", "Jh", "10h", "2d", "3c"])
    hand = HandEvaluator.evaluate(cards)
    assert hand.rank == HandRank.STRAIGHT_FLUSH

def test_four_of_a_kind():
    cards = create_cards(["Ah", "Ad", "As", "Ac", "Kd", "2d", "3c"])
    hand = HandEvaluator.evaluate(cards)
    assert hand.rank == HandRank.FOUR_OF_A_KIND

def test_full_house():
    cards = create_cards(["Ah", "Ad", "As", "Kd", "Ks", "2d", "3c"])
    hand = HandEvaluator.evaluate(cards)
    assert hand.rank == HandRank.FULL_HOUSE

def test_flush():
    cards = create_cards(["Ah", "2h", "5h", "9h", "Jh", "2d", "3c"])
    hand = HandEvaluator.evaluate(cards)
    assert hand.rank == HandRank.FLUSH

def test_straight():
    cards = create_cards(["9s", "8d", "7h", "6c", "5s", "2d", "3c"])
    hand = HandEvaluator.evaluate(cards)
    assert hand.rank == HandRank.STRAIGHT

def test_straight_wheel():
    # A-2-3-4-5
    cards = create_cards(["Ah", "2d", "3h", "4c", "5s", "9d", "Kd"])
    hand = HandEvaluator.evaluate(cards)
    assert hand.rank == HandRank.STRAIGHT
    # Wheelのstraight_highは5
    assert hand.tiebreakers[0] == 5

def test_three_of_a_kind():
    cards = create_cards(["Ah", "Ad", "As", "9c", "5s", "2d", "3c"])
    hand = HandEvaluator.evaluate(cards)
    assert hand.rank == HandRank.THREE_OF_A_KIND

def test_two_pair():
    cards = create_cards(["Ah", "Ad", "Ks", "Kc", "5s", "2d", "3c"])
    hand = HandEvaluator.evaluate(cards)
    assert hand.rank == HandRank.TWO_PAIR

def test_one_pair():
    cards = create_cards(["Ah", "Ad", "Qc", "9s", "5s", "2d", "3c"])
    hand = HandEvaluator.evaluate(cards)
    assert hand.rank == HandRank.ONE_PAIR

def test_high_card():
    cards = create_cards(["Ah", "Qd", "9s", "7c", "5s", "2d", "3c"])
    hand = HandEvaluator.evaluate(cards)
    assert hand.rank == HandRank.HIGH_CARD

def test_compare_hands():
    # Flush vs Straight
    flush_hand = HandEvaluator.evaluate(create_cards(["Ah", "Jh", "9h", "5h", "2h", "2d", "3c"]))
    straight_hand = HandEvaluator.evaluate(create_cards(["9s", "8d", "7h", "6c", "5s", "2d", "3c"]))
    assert HandEvaluator.compare(flush_hand, straight_hand) > 0 # Flush wins

    # Same rank, kicker difference
    # Correcting inputs for precise comparison test
    h1 = HandEvaluator.evaluate(create_cards(["Ah", "Ad", "Ks", "9c", "8d", "2c", "3s"])) # Pair A, Kickers K, 9, 8
    h2 = HandEvaluator.evaluate(create_cards(["Ah", "Ad", "Ks", "7c", "6d", "2c", "3s"])) # Pair A, Kickers K, 7, 6
    
    assert HandEvaluator.compare(h1, h2) > 0
