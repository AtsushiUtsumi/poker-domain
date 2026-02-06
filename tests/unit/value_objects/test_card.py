from poker_domain.value_objects.card import Card, Suit, Rank

def test_card_creation():
    card = Card(Suit.HEARTS, Rank.ACE)
    assert card.suit == Suit.HEARTS
    assert card.rank == Rank.ACE
    assert card.rank.value == 14

def test_card_string_representation():
    card = Card(Suit.SPADES, Rank.KING)
    assert str(card) == "KING of SPADES"

def test_enums():
    assert Suit.HEARTS.value == "hearts"
    assert Rank.TWO.value == 2
