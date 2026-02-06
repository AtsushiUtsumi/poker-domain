import pytest
from poker_domain.value_objects.chips import Chips

def test_chips_creation():
    chips = Chips(100)
    assert chips.amount == 100

def test_chips_negative_value():
    with pytest.raises(ValueError):
        Chips(-10)

def test_chips_add():
    c1 = Chips(100)
    c2 = Chips(50)
    result = c1 + c2
    assert result.amount == 150

def test_chips_sub():
    c1 = Chips(100)
    c2 = Chips(30)
    result = c1 - c2
    assert result.amount == 70

def test_chips_sub_negative_result():
    c1 = Chips(50)
    c2 = Chips(100)
    with pytest.raises(ValueError):
        _ = c1 - c2

def test_chips_comparison():
    c1 = Chips(100)
    c2 = Chips(200)
    c3 = Chips(100)
    
    assert c1 < c2
    assert c2 > c1
    assert c1 == c3
    assert c1 <= c3
    assert c1 >= c3

def test_chips_repr():
    c = Chips(500)
    assert repr(c) == "Chips(500)"
