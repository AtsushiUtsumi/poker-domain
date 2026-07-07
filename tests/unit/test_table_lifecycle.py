from unittest.mock import patch

import pytest

from poker_domain.table import PokerTable
from poker_domain.value_objects.chips import Chips
from poker_domain.value_objects.action import Call, Check
from poker_domain.game_state import GamePhase, TableStatus
from poker_domain.exceptions import TableClosedError


def test_blind_level_up():
    table = PokerTable(
        table_id="t1",
        max_players=2,
        blind_schedule=[(10, 20), (20, 40), (50, 100)],
    )
    assert table.get_state().small_blind == Chips(10)
    assert table.get_state().big_blind == Chips(20)
    assert table.get_state().blind_level == 0

    event = table.level_up_blind()
    assert event.payload["level"] == 1
    assert table.get_state().small_blind == Chips(20)
    assert table.get_state().big_blind == Chips(40)

    table.level_up_blind()
    assert table.get_state().blind_level == 2

    # 最終レベル到達後は据え置き
    table.level_up_blind()
    assert table.get_state().blind_level == 2
    assert table.get_state().small_blind == Chips(50)
    assert table.get_state().big_blind == Chips(100)


def test_ante_level_up_and_collection():
    table = PokerTable(
        table_id="t1",
        max_players=2,
        small_blind=10,
        big_blind=20,
        ante_schedule=[0, 5],
    )
    assert table.get_state().ante == Chips(0)

    table.add_player("a", Chips(1000))
    table.add_player("b", Chips(1000))

    table.level_up_ante()
    assert table.get_state().ante_level == 1
    assert table.get_state().ante == Chips(5)

    result = table.start_game()
    # SB(10) + BB(20) + ante(5) * 2人
    assert result.state.pot.amount == 40


def test_table_closes_when_all_players_leave():
    table = PokerTable(table_id="t1", max_players=2)
    assert table.get_table_status() == TableStatus.RECRUITING

    table.add_player("a", Chips(100))
    table.remove_player("a")

    assert table.get_table_status() == TableStatus.CLOSED
    with pytest.raises(TableClosedError):
        table.add_player("b", Chips(100))
    with pytest.raises(TableClosedError):
        table.start_game()


def test_fresh_empty_table_is_not_closed():
    """誰も座ったことのない新規テーブルは参加募集中であり、クローズ扱いにしない"""
    table = PokerTable(table_id="t1", max_players=2)
    assert table.get_table_status() == TableStatus.RECRUITING


def test_table_closes_on_heads_up_bust():
    with patch("poker_domain.deck.random.shuffle", lambda cards: None):
        table = PokerTable(
            table_id="t1", max_players=2, small_blind=10, big_blind=20,
        )
        table.add_player("big_stack", Chips(1000))
        table.add_player("short_stack", Chips(20))  # ちょうどBB分だけ持参

        result = table.start_game()
        assert result.state.phase == GamePhase.PRE_FLOP
        assert result.state.current_player_id == "big_stack"

        result = table.action("big_stack", Call())
        assert result.state.phase == GamePhase.FLOP

        result = table.action("big_stack", Check())
        assert result.state.phase == GamePhase.TURN

        result = table.action("big_stack", Check())
        assert result.state.phase == GamePhase.RIVER

        result = table.action("big_stack", Check())
        assert result.state.phase == GamePhase.SHOWDOWN
        assert result.state.status == TableStatus.CLOSED
        assert table.get_table_status() == TableStatus.CLOSED

        with pytest.raises(TableClosedError):
            table.start_game()
