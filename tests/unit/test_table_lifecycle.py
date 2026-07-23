from unittest.mock import patch

import pytest

from poker_domain.exceptions import InvalidBuyInError, RebuyNotAllowedError, TableClosedError
from poker_domain.game_state import GamePhase, TableStatus
from poker_domain.table import PokerTable
from poker_domain.value_objects.action import Call, Check, Fold, Raise
from poker_domain.value_objects.card import Card, Rank, Suit
from poker_domain.value_objects.chips import Chips


def _stacked_deck(order: list[Card]):
    """random.shuffle を差し替えて、指定した順にカードが配られるようにする"""
    def fake_shuffle(cards: list[Card]) -> None:
        remaining = [c for c in cards if c not in order]
        cards[:] = order + remaining
    return patch("poker_domain.deck.random.shuffle", fake_shuffle)


def test_no_level_schedule_uses_single_level_from_arguments():
    """level_schedule 未指定時は small_blind/big_blind/ante の単一レベルで初期化される"""
    table = PokerTable(
        table_id="t1", max_players=2, small_blind=10, big_blind=20, ante=5,
    )
    assert table.get_state().small_blind == Chips(10)
    assert table.get_state().big_blind == Chips(20)
    assert table.get_state().ante == Chips(5)
    assert table.get_state().level == 0

    # 唯一(かつ最終)のレベルなので level_up() を呼んでも変化しない
    table.level_up()
    assert table.get_state().level == 0
    assert table.get_state().small_blind == Chips(10)
    assert table.get_state().big_blind == Chips(20)
    assert table.get_state().ante == Chips(5)


def test_level_up_advances_blind_and_ante_together():
    """level_schedule 指定時、level_up() のたびに SB/BB/アンティがまとめて次のレベルに進む"""
    table = PokerTable(
        table_id="t1",
        max_players=2,
        level_schedule=[(10, 20, 0), (20, 40, 5), (50, 100, 10)],
    )
    assert table.get_state().small_blind == Chips(10)
    assert table.get_state().big_blind == Chips(20)
    assert table.get_state().ante == Chips(0)
    assert table.get_state().level == 0

    event = table.level_up()
    assert event.payload == {"level": 1, "small_blind": 20, "big_blind": 40, "ante": 5}
    assert table.get_state().level == 1
    assert table.get_state().small_blind == Chips(20)
    assert table.get_state().big_blind == Chips(40)
    assert table.get_state().ante == Chips(5)

    table.level_up()
    assert table.get_state().level == 2
    assert table.get_state().small_blind == Chips(50)
    assert table.get_state().big_blind == Chips(100)
    assert table.get_state().ante == Chips(10)

    # 最終レベル到達後は据え置き
    table.level_up()
    assert table.get_state().level == 2
    assert table.get_state().small_blind == Chips(50)
    assert table.get_state().big_blind == Chips(100)
    assert table.get_state().ante == Chips(10)


def test_level_up_ante_is_collected_at_next_hand():
    table = PokerTable(
        table_id="t1",
        max_players=2,
        level_schedule=[(10, 20, 0), (10, 20, 5)],
    )
    table.add_player("a", Chips(1000))
    table.add_player("b", Chips(1000))

    table.level_up()
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


# 配布順は「ディーラーの次のプレイヤー」から1枚ずつ。heads-upではdealer=big_stack(index0)なので
# 各ラウンドの最初の1枚は short_stack (index1) に配られる。
# big_stack: A♠A♣ (勝ち) / short_stack: 2♥2♦ (負け) / ボードはどちらにも絡まないブリック
_HEADS_UP_DECK = [
    Card(Suit.HEARTS, Rank.TWO),    # short_stack hole1
    Card(Suit.SPADES, Rank.ACE),    # big_stack hole1
    Card(Suit.DIAMONDS, Rank.TWO),  # short_stack hole2
    Card(Suit.CLUBS, Rank.ACE),     # big_stack hole2
    Card(Suit.HEARTS, Rank.SEVEN),  # flop
    Card(Suit.DIAMONDS, Rank.NINE),
    Card(Suit.CLUBS, Rank.FOUR),
    Card(Suit.SPADES, Rank.SIX),    # turn
    Card(Suit.HEARTS, Rank.JACK),   # river
]


def test_table_closes_on_heads_up_bust():
    with _stacked_deck(_HEADS_UP_DECK):
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


# 3人サイドポットシナリオ:
#   A: A♠A♣ (最強、15チップしか持たずオールイン)
#   B: K♠K♣ (2番手)
#   C: 4♠4♣ (最弱)
#   ボードはいずれのハンドにも絡まないブリック
_SIDE_POT_DECK = [
    Card(Suit.SPADES, Rank.KING),    # B hole1
    Card(Suit.SPADES, Rank.FOUR),    # C hole1
    Card(Suit.SPADES, Rank.ACE),     # A hole1
    Card(Suit.CLUBS, Rank.KING),     # B hole2
    Card(Suit.CLUBS, Rank.FOUR),     # C hole2
    Card(Suit.CLUBS, Rank.ACE),      # A hole2
    Card(Suit.DIAMONDS, Rank.TWO),   # flop
    Card(Suit.HEARTS, Rank.FIVE),
    Card(Suit.DIAMONDS, Rank.SEVEN),
    Card(Suit.SPADES, Rank.NINE),    # turn
    Card(Suit.HEARTS, Rank.JACK),    # river
]


def test_side_pot_distribution_for_uneven_all_in():
    with _stacked_deck(_SIDE_POT_DECK):
        table = PokerTable(
            table_id="t1", max_players=3, small_blind=10, big_blind=20,
        )
        table.add_player("a", Chips(15))     # ショートスタック
        table.add_player("b", Chips(1000))
        table.add_player("c", Chips(1000))

        result = table.start_game()
        # 3人卓: dealer=A, SB=B(10), BB=C(20), 開始プレイヤー=A
        assert result.state.pot.amount == 30
        assert result.state.current_player_id == "a"

        # A: 15チップしかないので Call はオールインとして成立する
        result = table.action("a", Call())
        assert result.state.players[0].is_all_in is True
        assert result.state.pot.amount == 45

        # B: 100 にレイズ (A のオールイン額を超える → サイドポット発生)
        result = table.action("b", Raise(amount=100))
        # C: コール
        result = table.action("c", Call())
        assert result.state.phase == GamePhase.FLOP
        assert result.state.pot.amount == 215  # 15 + 100 + 100

        # FLOP -> TURN -> RIVER の3ストリート分チェックし合う
        for _ in range(3):
            for pid in ("b", "c"):
                result = table.action(pid, Check())

        assert result.state.phase == GamePhase.SHOWDOWN

        showdown_event = next(
            e for e in result.events if e.event_type.name == "SHOWDOWN"
        )
        payouts = showdown_event.payload["payouts"]

        # メインポット(45, A/B/C対象) は最強ハンドの A が獲得
        # サイドポット(170, B/C のみ対象) は B が獲得 (A は対象外)
        assert payouts == {"a": 45, "b": 170}

        final_state = table.get_state()
        chips_by_id = {p.player_id: p.chips.amount for p in final_state.players}
        assert chips_by_id["a"] == 45       # 0 (all-in) + 45
        assert chips_by_id["b"] == 1000 - 100 + 170
        assert chips_by_id["c"] == 1000 - 100


def test_rake_is_deducted_at_showdown():
    with _stacked_deck(_HEADS_UP_DECK):
        table = PokerTable(
            table_id="t1", max_players=2, small_blind=10, big_blind=20,
            rake_percent=0.1, rake_cap=5,
        )
        table.add_player("big_stack", Chips(1000))
        table.add_player("short_stack", Chips(20))

        table.start_game()
        table.action("big_stack", Call())
        table.action("big_stack", Check())
        table.action("big_stack", Check())
        result = table.action("big_stack", Check())

        showdown_event = next(
            e for e in result.events if e.event_type.name == "SHOWDOWN"
        )
        # ポットは40、レーキ10%=4だがキャップ5未満なのでそのまま4
        assert showdown_event.payload["rake"] == 4
        assert showdown_event.payload["payouts"]["big_stack"] == 36


def test_no_rake_on_uncontested_fold_win():
    table = PokerTable(
        table_id="t1", max_players=2, small_blind=10, big_blind=20,
        rake_percent=0.5,
    )
    table.add_player("a", Chips(1000))
    table.add_player("b", Chips(1000))

    table.start_game()
    result = table.action("a", Fold())

    showdown_event = next(
        e for e in result.events if e.event_type.name == "SHOWDOWN"
    )
    assert showdown_event.payload["rake"] == 0
    # 不戦勝はポット全額 (SB10+BB20=30) がそのまま渡る
    assert showdown_event.payload["payouts"]["b"] == 30


# 3人卓でバストが発生した後にディーラーローテーションが正しく次ハンドに進めるかのシナリオ:
#   ハンド1: dealer=a, SB=b, BB=c。a, b が降りて c の不戦勝 (誰もバストしない)
#   ハンド2: dealer=b, SB=c, BB=a。c がオールインし最弱ハンド (4-4) で敗北してバスト
#   ハンド3: バストした c を除外し、a, b の2人でハンドが正しく開始できることを確認する
_BUST_ROTATION_DECK = [
    Card(Suit.SPADES, Rank.FOUR),    # c hole1
    Card(Suit.SPADES, Rank.ACE),     # a hole1
    Card(Suit.SPADES, Rank.KING),    # b hole1
    Card(Suit.CLUBS, Rank.FOUR),     # c hole2
    Card(Suit.CLUBS, Rank.ACE),      # a hole2
    Card(Suit.CLUBS, Rank.KING),     # b hole2
    Card(Suit.DIAMONDS, Rank.TWO),   # flop
    Card(Suit.HEARTS, Rank.FIVE),
    Card(Suit.DIAMONDS, Rank.SEVEN),
    Card(Suit.SPADES, Rank.NINE),    # turn
    Card(Suit.HEARTS, Rank.JACK),    # river
]


def test_three_handed_game_progresses_after_a_player_busts():
    with _stacked_deck(_BUST_ROTATION_DECK):
        table = PokerTable(
            table_id="t1", max_players=3, small_blind=10, big_blind=20,
        )
        table.add_player("a", Chips(1000))
        table.add_player("b", Chips(1000))
        table.add_player("c", Chips(100))

        # ── ハンド1: dealer=a, SB=b, BB=c。a, b が降りて c の不戦勝 ──
        table.start_game()
        table.action("a", Fold())
        result = table.action("b", Fold())
        assert result.state.phase == GamePhase.SHOWDOWN

        # ── ハンド2: dealer=b, SB=c, BB=a。c がオールインして敗北しバストする ──
        result = table.start_game()
        assert result.state.current_player_id == "b"

        table.action("b", Call())
        table.action("c", Raise(amount=110))  # c の残りチップ全額でオールイン
        table.action("a", Call())
        result = table.action("b", Call())
        assert result.state.phase == GamePhase.FLOP

        for _ in range(3):
            for pid in ("a", "b"):
                result = table.action(pid, Check())

        assert result.state.phase == GamePhase.SHOWDOWN
        chips_by_id = {p.player_id: p.chips.amount for p in table.get_state().players}
        assert chips_by_id["c"] == 0  # A-A の a が勝ち、4-4 の c はバスト

        # ── ハンド3: バストした c を除いて a, b だけで正常に開始できること ──
        result = table.start_game()
        assert result.state.phase == GamePhase.PRE_FLOP
        remaining_ids = {p.player_id for p in result.state.players}
        assert remaining_ids == {"a", "b"}
        assert result.state.current_player_id == "a"
        assert result.state.pot.amount == 30  # SB(10) + BB(20)


def test_rebuy_disallowed_after_bust_when_allow_rebuy_is_false():
    """allow_rebuy=False の卓では、バストして除外されたプレイヤーIDは再度 add_player できない"""
    with _stacked_deck(_BUST_ROTATION_DECK):
        table = PokerTable(
            table_id="t1", max_players=3, small_blind=10, big_blind=20,
            allow_rebuy=False,
        )
        table.add_player("a", Chips(1000))
        table.add_player("b", Chips(1000))
        table.add_player("c", Chips(100))

        # ── ハンド1: a, b が降りて c の不戦勝 (誰もバストしない) ──
        table.start_game()
        table.action("a", Fold())
        table.action("b", Fold())

        # ── ハンド2: c がオールインして敗北しバストする ──
        table.start_game()
        table.action("b", Call())
        table.action("c", Raise(amount=110))
        table.action("a", Call())
        result = table.action("b", Call())
        assert result.state.phase == GamePhase.FLOP

        for _ in range(3):
            for pid in ("a", "b"):
                result = table.action(pid, Check())
        assert result.state.phase == GamePhase.SHOWDOWN

        # ── ハンド3: バストした c を除外する後片付けが start_game() 内で走り、a, b のみで開始 ──
        result = table.start_game()
        assert result.state.phase == GamePhase.PRE_FLOP
        current = result.state.current_player_id
        result = table.action(current, Fold())  # 即座に不戦勝で SHOWDOWN へ
        assert result.state.phase == GamePhase.SHOWDOWN

        with pytest.raises(RebuyNotAllowedError):
            table.add_player("c", Chips(500))


def test_rebuy_disallowed_immediately_after_bust_before_next_start_game():
    """SHOWDOWN直後、次の start_game() を呼ぶ前に remove_player→add_player した場合でも
    allow_rebuy=False なら RebuyNotAllowedError になるべき"""
    with _stacked_deck(_BUST_ROTATION_DECK):
        table = PokerTable(
            table_id="t1", max_players=3, small_blind=10, big_blind=20,
            allow_rebuy=False,
        )
        table.add_player("a", Chips(1000))
        table.add_player("b", Chips(1000))
        table.add_player("c", Chips(100))

        table.start_game()
        table.action("a", Fold())
        table.action("b", Fold())

        table.start_game()
        table.action("b", Call())
        table.action("c", Raise(amount=110))
        table.action("a", Call())
        result = table.action("b", Call())
        assert result.state.phase == GamePhase.FLOP

        for _ in range(3):
            for pid in ("a", "b"):
                result = table.action(pid, Check())
        assert result.state.phase == GamePhase.SHOWDOWN

        # ここがポイント: 次の start_game() を呼ぶ前に、バストした c を rebuy しようとする
        table.remove_player("c")
        with pytest.raises(RebuyNotAllowedError):
            table.add_player("c", Chips(100))


def test_rebuy_allowed_for_voluntary_leave_even_when_disallowed():
    """バスト経由ではない自発的な離脱者は、allow_rebuy=False でも再入場できる"""
    table = PokerTable(table_id="t1", max_players=2, allow_rebuy=False)
    table.add_player("a", Chips(1000))
    table.add_player("b", Chips(1000))
    table.remove_player("b")

    event = table.add_player("b", Chips(1000))
    assert event.payload["player_id"] == "b"


def test_fixed_buy_in_rejects_mismatched_amount():
    table = PokerTable(table_id="t1", max_players=3, fixed_buy_in=1000)

    with pytest.raises(InvalidBuyInError):
        table.add_player("a", Chips(500))

    event = table.add_player("a", Chips(1000))
    assert event.payload["player_id"] == "a"


def test_no_fixed_buy_in_allows_any_amount():
    table = PokerTable(table_id="t1", max_players=3)

    table.add_player("a", Chips(100))
    table.add_player("b", Chips(9999))

    chips_by_id = {p.player_id: p.chips.amount for p in table.get_state().players}
    assert chips_by_id == {"a": 100, "b": 9999}


def test_fixed_buy_in_also_applies_to_later_add_player():
    """固定バイイン額の制約は、ハンドが一度進行した後の add_player にも継続して適用される"""
    table = PokerTable(
        table_id="t1", max_players=3, small_blind=10, big_blind=20,
        fixed_buy_in=1000,
    )
    table.add_player("a", Chips(1000))
    table.add_player("b", Chips(1000))

    result = table.start_game()
    result = table.action(result.state.current_player_id, Fold())  # 不戦勝で即 SHOWDOWN へ
    assert result.state.phase == GamePhase.SHOWDOWN

    with pytest.raises(InvalidBuyInError):
        table.add_player("newcomer", Chips(500))

    event = table.add_player("newcomer", Chips(1000))
    assert event.payload["player_id"] == "newcomer"


def test_get_state_survives_remove_player_after_showdown_when_indices_become_stale():
    """2人卓でハンドを1回消化 (SHOWDOWN) した後、_current_player_index と _dealer_index が
    異なるプレイヤーを指している状態で、そのどちらでもないプレイヤー (dealer 側) が
    remove_player() で離脱しても get_state() がクラッシュしないこと。

    heads-up では pre-flop はディーラー(index0) から、post-flop は非ディーラー(index1) から
    行動するため、flop で b (index1) が fold すると current_player_index=1 (b), dealer_index=0
    (a) のまま SHOWDOWN になる。この状態で a (index0) を remove すると、生存者 b は新しい
    リストの index0 にずれるが、古い _current_player_index=1 は縮んだリストに対して範囲外になる。
    """
    table = PokerTable(table_id="t1", max_players=2, small_blind=10, big_blind=20)
    table.add_player("a", Chips(1000))
    table.add_player("b", Chips(1000))

    table.start_game()
    table.action("a", Call())
    result = table.action("b", Check())
    assert result.state.phase == GamePhase.FLOP

    result = table.action("b", Fold())
    assert result.state.phase == GamePhase.SHOWDOWN
    assert result.state.current_player_id == "b"
    assert result.state.dealer_id == "a"

    table.remove_player("a")

    state = table.get_state()  # 内部 _snapshot() が古いインデックスで例外を投げないこと
    assert [p.player_id for p in state.players] == ["b"]
    assert state.current_player_id == "b"
    assert state.dealer_id == "b"


def test_remove_player_not_referenced_by_indices_does_not_break_state():
    """3人卓で、_current_player_index/_dealer_index のどちらも指していないプレイヤーが
    離脱するケース (インデックスの再計算が本来不要なはず) でも状態が壊れないこと。
    """
    table = PokerTable(table_id="t1", max_players=3, small_blind=10, big_blind=20)
    table.add_player("a", Chips(1000))
    table.add_player("b", Chips(1000))
    table.add_player("c", Chips(1000))

    table.start_game()
    table.action("a", Fold())
    result = table.action("b", Fold())
    assert result.state.phase == GamePhase.SHOWDOWN
    # 不戦勝の c が current_player_id にも dealer_id にもならないことを前提とする
    assert result.state.current_player_id == "b"
    assert result.state.dealer_id == "a"

    table.remove_player("c")

    state = table.get_state()
    assert {p.player_id for p in state.players} == {"a", "b"}
    assert state.current_player_id == "b"
    assert state.dealer_id == "a"
