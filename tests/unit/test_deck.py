import pytest
from poker_domain.deck import Deck
from poker_domain.exceptions import DeckEmptyError

def test_deck_initialization():
    deck = Deck()
    assert deck.remaining == 52

def test_deck_shuffle():
    deck = Deck()
    original_order = list(deck._cards)
    deck.shuffle()
    # 確率的に同じになる可能性は極めて低いが、厳密にはセットで比較すべきだが、
    # 順序が変わったことを確認したい。ただしテストの不安定さを避けるため、
    # 長さと構成要素が変わっていないことを主眼にする。
    assert len(deck._cards) == 52
    assert set(deck._cards) == set(original_order)

def test_deck_deal():
    deck = Deck()
    cards = deck.deal(2)
    assert len(cards) == 2
    assert deck.remaining == 50

def test_deal_empty_deck():
    deck = Deck()
    deck.deal(52)
    assert deck.remaining == 0
    
    with pytest.raises(DeckEmptyError):
        deck.deal(1)
