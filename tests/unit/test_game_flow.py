from poker_domain.table import PokerTable
from poker_domain.value_objects.chips import Chips
from poker_domain.value_objects.action import Call, Check
from poker_domain.game_state import GamePhase

def test_full_game_flow():
    # 1. テーブル作成
    table = PokerTable(
        table_id="test_table",
        max_players=3,
        small_blind=10,
        big_blind=20
    )
    
    # 2. プレイヤー3人参加
    players = ["player_a", "player_b", "player_c"]
    for pid in players:
        table.add_player(player_id=pid, chips=Chips(1000))

    # 3. ゲーム開始 (Hand Start)
    result = table.start_game()
    
    # 期待: Dealer=A, SB=B, BB=C. 
    # Action順: A (Dealer/Button) -> B (SB) -> C (BB) 
    
    assert result.state.phase == GamePhase.PRE_FLOP
    assert result.state.current_player_id == "player_a"
    assert result.state.pot.amount == 30  # SB(10) + BB(20)

    # 4. Pre-Flop Actions
    # Player A: Call (20)
    result = table.action("player_a", Call())
    assert result.state.current_player_id == "player_b"
    
    # Player B: Call (Need 10 more to match 20)
    result = table.action("player_b", Call())
    assert result.state.current_player_id == "player_c"
    
    # Player C: Check (Already matched 20)
    result = table.action("player_c", Check())
    
    # ラウンド終了 -> Flopへ
    assert result.state.phase == GamePhase.FLOP
    
    # Flop Action順: SB(B) -> BB(C) -> Button(A)
    assert result.state.current_player_id == "player_b"
    
    # 全員チェック
    result = table.action("player_b", Check())
    result = table.action("player_c", Check())
    result = table.action("player_a", Check())
    
    # ラウンド終了 -> Turnへ
    assert result.state.phase == GamePhase.TURN
    
    # 全員チェック
    result = table.action("player_b", Check())
    result = table.action("player_c", Check())
    result = table.action("player_a", Check())

    # ラウンド終了 -> Riverへ
    assert result.state.phase == GamePhase.RIVER

    # 全員チェック
    result = table.action("player_b", Check())
    result = table.action("player_c", Check())
    result = table.action("player_a", Check())

    # ラウンド終了 -> Showdown
    assert result.state.phase == GamePhase.SHOWDOWN
    
    # 結果確認
    winner_id = None
    for event in result.events:
        if event.event_type.name == "SHOWDOWN":
            winner_id = event.payload.get("winner_id")
            
    assert winner_id is not None
