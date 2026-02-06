from poker_domain.table import PokerTable
from poker_domain.value_objects.chips import Chips
from poker_domain.value_objects.action import Call, Check
from poker_domain.game_state import GamePhase

def test_simulation():
    # 1. テーブル作成
    print("--- テーブル作成 ---")
    table = PokerTable(
        table_id="test_table",
        max_players=3,
        small_blind=10,
        big_blind=20
    )
    
    # 2. プレイヤー3人参加
    print("--- プレイヤー参加 ---")
    players = ["player_a", "player_b", "player_c"]
    for pid in players:
        table.add_player(player_id=pid, chips=Chips(1000))
        print(f"{pid} joined with 1000 chips.")

    # 3. ゲーム開始 (Hand Start)
    print("\n--- ゲーム開始 (Pre-Flop) ---")
    result = table.start_game()
    print_state(result.state)
    
    # 期待: Dealer=A, SB=B, BB=C. 
    # Action順: A (Dealer/Button) -> B (SB) -> C (BB) 
    # ※ start_gameのロジックで3人の場合、Dealer+3 = 0(A) からスタート
    
    assert result.state.phase == GamePhase.PRE_FLOP
    assert result.state.current_player_id == "player_a"
    assert result.state.pot.amount == 30  # SB(10) + BB(20)

    # 4. Pre-Flop Actions
    # Player A: Call (20)
    print("\n> Player A calls")
    result = table.action("player_a", Call())
    assert result.state.current_player_id == "player_b"
    
    # Player B: Call (Need 10 more to match 20)
    print("> Player B calls")
    result = table.action("player_b", Call())
    assert result.state.current_player_id == "player_c"
    
    # Player C: Check (Already matched 20)
    print("> Player C checks")
    result = table.action("player_c", Check())
    
    # ラウンド終了 -> Flopへ
    assert result.state.phase == GamePhase.FLOP
    print("\n--- Flop ---")
    print(f"Community Cards: {result.state.community_cards}")
    print(f"Pot: {result.state.pot.amount}")
    
    # Flop Action順: SB(B) -> BB(C) -> Button(A)
    # Dealer=A. Next active is B.
    
    assert result.state.current_player_id == "player_b"
    
    # 全員チェック
    print("> Player B checks")
    result = table.action("player_b", Check())
    print("> Player C checks")
    result = table.action("player_c", Check())
    print("> Player A checks")
    result = table.action("player_a", Check())
    
    # ラウンド終了 -> Turnへ
    assert result.state.phase == GamePhase.TURN
    print("\n--- Turn ---")
    print(f"Community Cards: {result.state.community_cards}")
    
    # 全員チェック
    print("> Player B checks")
    result = table.action("player_b", Check())
    print("> Player C checks")
    result = table.action("player_c", Check())
    print("> Player A checks")
    result = table.action("player_a", Check())

    # ラウンド終了 -> Riverへ
    assert result.state.phase == GamePhase.RIVER
    print("\n--- River ---")
    print(f"Community Cards: {result.state.community_cards}")

    # 全員チェック
    print("> Player B checks")
    result = table.action("player_b", Check())
    print("> Player C checks")
    result = table.action("player_c", Check())
    print("> Player A checks")
    result = table.action("player_a", Check())

    # ラウンド終了 -> Showdown
    print("\n--- Showdown ---")
    assert result.state.phase == GamePhase.SHOWDOWN
    
    # 結果確認
    # イベントから勝者を取得
    winner_id = None
    for event in result.events:
        if event.event_type.name == "SHOWDOWN":
            winner_id = event.payload.get("winner_id")
            hands = event.payload.get("hands")
            print(f"Winner: {winner_id}")
            print(f"Hands: {hands}")

    assert winner_id is not None
    print("\nテスト完了: 正常にゲームが進行しました。")

def print_state(state):
    print(f"Phase: {state.phase.name}")
    print(f"Pot: {state.pot.amount}")
    print(f"Next Action: {state.current_player_id}")
