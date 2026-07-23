# poker_domain: プレイヤーごとのアクション履歴 (action_log) 追加依頼

## 背景・目的

`mullhouse` リポジトリの `bots/table_bot.py` にいるCPUボットで、「フロップでベットした相手がターンでチェックしてきたらベットする」といったマルチウェイでも安全に成立する戦略ロジックを組みたい。しかし現状は「ベットしたプレイヤー」と「チェックしたプレイヤー」が同一人物かどうかを判定する手段が存在しない。

ボットは `GET /state` のポーリングのみを利用しており、見えるのは `chips` / `current_bet` / `folded` などのスナップショットのみで、各プレイヤーが各ストリートでどんなアクション(fold/check/call/bet/raise)を取ったかの履歴が取得できない。`PLAYER_ACTED` イベントの payload も `{"player_id": ...}` のみでアクション種別を含んでいないため、events を購読しても再構築できない。

## 依頼内容

`GameState` に、進行中のハンド内でプレイヤーごとに何のアクションを取ったかを追跡できる `action_log` を追加してほしい。

### 1. 新しい値オブジェクト (`game_state.py`)

```python
@dataclass(frozen=True)
class ActionLogEntry:
    player_id: str
    phase: GamePhase       # アクションを取った時点のフェーズ (PRE_FLOP/FLOP/TURN/RIVER)
    action: str            # "fold" | "check" | "call" | "bet" | "raise"
    amount: int | None     # bet/raise の場合のみ金額、それ以外は None
```

### 2. `GameState` への追加

```python
@dataclass(frozen=True)
class GameState:
    ...
    action_log: tuple[ActionLogEntry, ...]
```

### 3. `PokerTable` (`table.py`) 側の実装

- `__init__` に `self._action_log: list[ActionLogEntry] = []` を追加する
- `start_game()` の「新ハンドの初期化」ブロック(`self._pot = Chips(0)` などをリセットしている箇所)で `self._action_log = []` にリセットする
- `action()` 内、`self._validate_action(...)` / `self._apply_action(...)` の直後で、今回のアクションを1件 `self._action_log` に追記する
  - `phase` は **advance前** の `self._phase`(= アクションを取った時点のフェーズ)を使う。`_advance_phase` はこのタイミングより後に呼ばれるため、素直に `self._phase` を参照すればよい
  - `action` 文字列は `poker_service.build_action` が使っているのと同じ小文字表記(`"fold"` / `"check"` / `"call"` / `"bet"` / `"raise"`)に合わせる
  - `amount` は `Bet` / `Raise` のときのみ `action.amount`、それ以外は `None`
- `_snapshot()` で `action_log=tuple(self._action_log)` を渡す

### 4. 対象外(今回は不要)

- ブラインド/アンティの自動徴収は「プレイヤーが選んだアクション」ではないため `action_log` には含めない(既存の `PLAYER_ACTED` イベントも同様にブラインド/アンティでは発火していない)
- ショーダウン後〜次ハンド開始前の履歴保持は不要。次の `start_game()` でリセットされる想定

## 影響範囲

- `game_state.py`: `ActionLogEntry` 追加、`GameState.action_log` フィールド追加
- `table.py`: `_action_log` の保持・リセット・追記・`_snapshot()` への反映
- 既存の `GameEvent(PLAYER_ACTED)` の payload は変更不要(据え置き)。破壊的変更なし

## mullhouse 側で追って対応すること(参考・今回のスコープ外)

- `backend/poker_service.py` の `serialize_state()` に `action_log` のシリアライズを追加

  ```python
  "action_log": [
      {"player_id": e.player_id, "phase": e.phase.name, "action": e.action, "amount": e.amount}
      for e in state.action_log
  ],
  ```

- `bots/table_bot.py` の `choose_action()` で、`state["action_log"]` から「フロップでベットしたプレイヤーIDが、ターンでもチェックしているか」を突き合わせる判定ロジックに置き換える
