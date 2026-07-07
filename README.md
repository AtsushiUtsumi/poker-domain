# poker-domain

ポーカー(テキサスホールデム)のドメインロジックを提供する Python ライブラリ。
UI・通信層を持たない純粋なコアロジックとして実装されており、サービス層から
`PokerTable` を介して呼び出すことを想定しています。

## インストール

```bash
pip install -e .
```

- Python 3.10 以上が必要 (`match` 文、`X | Y` 型ヒントを使用)
- 依存パッケージなし

## パッケージ構成

```
poker_domain/
├── __init__.py          # 公開 API のエクスポート
├── interfaces.py        # PokerTableInterface (抽象基底クラス)
├── table.py             # PokerTable (集約ルート・全ゲームロジック)
├── player.py            # Player (エンティティ)
├── deck.py              # Deck (52枚のカードデック)
├── hand_evaluator.py    # HandEvaluator (役の判定・比較)
├── game_state.py        # GameState などの不変スナップショット/イベント型
├── exceptions.py        # 例外階層
└── value_objects/
    ├── action.py        # Fold / Check / Call / Bet / Raise
    ├── card.py          # Card / Suit / Rank
    ├── chips.py         # Chips (非負整数のチップ量)
    └── hand.py          # Hand / HandRank
```

## アーキテクチャ

- **`PokerTable`** がテーブル1つ分のゲーム状態と進行ロジックを完全にカプセル化する集約ルート。
  外部からの窓口は `PokerTableInterface` に定義されたメソッドのみ。
- 状態は `GameState` / `PlayerState` などの **frozen dataclass によるイミュータブルなスナップショット**として返され、
  呼び出し側が内部状態を直接変更することはできません。
- カード・チップ・アクション・役といったドメイン概念は `value_objects/` 配下に値オブジェクトとして定義。
- ゲーム進行中に発生した出来事は `GameEvent` の列として `ActionResult.events` に記録されます。

## 公開 API

### `PokerTableInterface`

```python
class PokerTableInterface(ABC):
    def add_player(self, player_id: str, chips: Chips) -> GameEvent: ...
    def remove_player(self, player_id: str) -> GameEvent: ...
    def start_game(self) -> ActionResult: ...
    def action(self, player_id: str, action: Action) -> ActionResult: ...
    def get_state(self, viewer_player_id: str | None = None) -> GameState: ...
    def level_up_blind(self) -> GameEvent: ...
    def level_up_ante(self) -> GameEvent: ...
    def get_table_status(self) -> TableStatus: ...
```

`PokerTable` がこれを実装する唯一のクラスです。

### `PokerTable`

```python
PokerTable(
    table_id: str,
    max_players: int = 6,
    small_blind: int = 25,
    big_blind: int = 50,
    timeout_seconds: int = 30,
    blind_schedule: list[tuple[int, int]] | None = None,
    ante_schedule: list[int] | None = None,
)
```

- `blind_schedule` を渡すと `[(small_blind, big_blind), ...]` のレベル表として管理される
  (未指定時は `small_blind`/`big_blind` 引数を単一レベルとして使用)
- `ante_schedule` を渡すと `[ante, ...]` のレベル表として管理される (未指定時はアンティなし = レベル0固定)

| メソッド | 説明 |
|---|---|
| `add_player(player_id, chips)` | プレイヤーを着席させる。満席・進行中・重複参加・クローズ後はエラー |
| `remove_player(player_id)` | プレイヤーを離席させる。進行中は不可。全員離脱すると卓は自動的にクローズする |
| `start_game()` | ハンドを開始する。アンティ・ブラインド徴収 → ホールカード2枚配布 → PRE_FLOP開始。2人以上必要、クローズ後はエラー |
| `action(player_id, action)` | 現在の手番プレイヤーのアクションを適用し、次の状態を返す |
| `get_state(viewer_player_id=None)` | 現在の状態のスナップショットを取得。`viewer_player_id` を指定するとそのプレイヤーのホールカードのみ見える |
| `level_up_blind()` | ブラインドレベルを1段階上昇させる (次のハンドから適用。最終レベル到達後は据え置き) |
| `level_up_ante()` | アンティレベルを1段階上昇させる (次のハンドから適用。最終レベル到達後は据え置き) |
| `get_table_status()` | テーブルのライフサイクル状態 (`TableStatus`) を返す |

## ゲーム進行のルール

### フェーズ (`GamePhase`)

`WAITING → PRE_FLOP → FLOP → TURN → RIVER → SHOWDOWN`

- `SHOWDOWN` 後に再度 `start_game()` を呼ぶと、ディーラーボタンが1つ隣に回り、
  チップ0のプレイヤーが除外されて次のハンドが始まる。

### ブラインドとポジション

- 2人 (heads-up): ディーラー = SB、もう一方 = BB。PRE_FLOP はディーラー(SB)から開始
- 3人以上: ディーラーの次が SB、その次が BB。PRE_FLOP は BB の次のプレイヤーから開始
- FLOP 以降は、ディーラーの次のアクティブプレイヤーから開始
- アンティが設定されている場合、ブラインド徴収前に全プレイヤーから徴収されポットに加算される
  (チップ不足の場合は保有分のみ徴収し all-in 扱い)

### ブラインド/アンティレベル

- `level_up_blind()` / `level_up_ante()` を呼ぶたびにレベルが1段階進み、
  以降の `start_game()` で新しいブラインド額・アンティ額が適用される
  (呼び出し時点で進行中のハンドには影響しない)
- 最終レベルに到達した状態でさらに呼び出しても、レベルは進まず据え置きになる

### テーブルのライフサイクル (`TableStatus`)

`get_table_status()` (または `GameState.status`) で以下のいずれかを取得できる。

| 状態 | 意味 |
|---|---|
| `RECRUITING` | 参加募集中 (`WAITING`/`SHOWDOWN` フェーズ。プレイヤーの参加・離脱が可能) |
| `PLAYING` | ハンド進行中 (`PRE_FLOP`〜`RIVER`) |
| `CLOSED` | クローズ。以下のいずれかで自動的に遷移し、以後 `add_player()` / `start_game()` は `TableClosedError` になる |
| `OTHER` | 上記いずれにも該当しない状態 (現状は到達しない予備区分) |

クローズに至る条件:
- 一度でもプレイヤーが着席したテーブルで、`remove_player()` により全員が離脱した場合
- ハンド終了後、チップを保有する生存プレイヤーが1人以下になった場合
  (人数に関わらず、その時点で対戦相手がいなくなった全てのケースを含む)

### アクション (`value_objects/action.py`)

| アクション | 条件 |
|---|---|
| `Fold()` | いつでも可能 |
| `Check()` | 自分のベット額が現在のベット額と同じ場合のみ |
| `Call()` | 差額分のチップを保有している場合のみ |
| `Bet(amount)` | 現在ベットが0のときのみ。最小額はビッグブラインド |
| `Raise(amount)` | 現在ベットがある場合のみ。最小レイズは現在ベットの2倍 |

チップが尽きると自動的に `is_all_in` になります。`Bet`/`Raise` が入ると、
他のアクティブプレイヤー全員が再度アクション対象 (`players_to_act`) に戻ります。

ラウンドが終了すると:
- 全員フォールドで1人残った場合 → その場で勝者にポットが渡り `SHOWDOWN` へ
- 全員 all-in の場合 → 残りのコミュニティカードを一気に配ってショーダウン
- `RIVER` のラウンド終了 → ショーダウンして役を比較し、最強のプレイヤーがポットを獲得
  (**同点によるスプリットポットは未対応**)
- それ以外 → 次のフェーズに進み、コミュニティカードを配布 (FLOP:3枚、TURN/RIVER:各1枚)

### 役の判定 (`HandEvaluator`)

- `evaluate(cards)`: 7枚 (ホール2枚 + コミュニティ5枚) から最も強い5枚の組み合わせを`Hand`として返す
- `compare(hand_a, hand_b)`: 正なら a が強い、負なら b が強い、0 で同点
- 役の強さは `HandRank` (`HIGH_CARD` 〜 `ROYAL_FLUSH`) の `IntEnum` で表現され、
  同ランク時は `tiebreakers` (比較用ランクの降順タプル) で比較する
- ホイールストレート (A-2-3-4-5) にも対応 (最上位カードは5として扱う)

## 値オブジェクト

- **`Card(suit, rank)`**: `Suit` (HEARTS/DIAMONDS/CLUBS/SPADES) と `Rank` (TWO(2) 〜 ACE(14)) の組。frozen dataclass
- **`Chips(amount)`**: 非負整数のチップ量。`+` `-` `<` `<=` `>` `>=` の演算子をサポートし、負になる操作は `ValueError`
- **`Hand(cards, rank, tiebreakers)`**: 評価済みの5枚の手
- **`Action`**: `Fold | Check | Call | Bet | Raise` の Union型

## 状態・イベント型 (`game_state.py`)

- **`GameState`**: テーブル全体の不変スナップショット (フェーズ、ポット、コミュニティカード、各プレイヤー状態、現在の手番、
  `small_blind`/`big_blind`/`ante`、`blind_level`/`ante_level`、`status` (`TableStatus`) など)
- **`PlayerState`**: プレイヤー1人分のスナップショット。`hole_cards` は showdown時、または
  `get_state()` の `viewer_player_id` と一致する場合のみ公開される
- **`ActionResult`**: `action()` / `start_game()` の戻り値。`state` (最新スナップショット)、
  `events` (発生したイベント列)、`waiting_for` (次に誰の・どのアクションを待っているか。ゲーム終了時は `None`)
- **`GameEvent`** / **`EventType`**: `PLAYER_JOINED` / `PLAYER_LEFT` / `GAME_STARTED` / `HAND_DEALT` /
  `PLAYER_ACTED` / `ROUND_ENDED` / `COMMUNITY_DEALT` / `TURN_CHANGED` / `SHOWDOWN` /
  `BLIND_LEVEL_UP` / `ANTE_LEVEL_UP` / `TABLE_CLOSED`
- **`WaitingFor`**: 次の手番プレイヤーID、取り得るアクション型のタプル、タイムアウト秒数
- **`TableStatus`**: `RECRUITING` / `PLAYING` / `CLOSED` / `OTHER` (テーブルのライフサイクル状態。詳細は上記参照)

## 例外 (`exceptions.py`)

`PokerError` を基底に以下が定義されています。

- `InvalidActionError` (→ `InsufficientChipsError`)
- `InvalidPlayerError`
- `TableFullError`
- `NotEnoughPlayersError`
- `GameAlreadyStartedError`
- `DeckEmptyError`
- `TableClosedError`

## 使用例

```python
from poker_domain import PokerTable, Chips, Call, Check

table = PokerTable(table_id="t1", max_players=3, small_blind=10, big_blind=20)

for pid in ["player_a", "player_b", "player_c"]:
    table.add_player(player_id=pid, chips=Chips(1000))

result = table.start_game()
print(result.state.phase)             # GamePhase.PRE_FLOP
print(result.state.current_player_id) # "player_a"

result = table.action("player_a", Call())
result = table.action("player_b", Call())
result = table.action("player_c", Check())
print(result.state.phase)             # GamePhase.FLOP

# ブラインド/アンティレベルの上昇 (次のハンドから反映)
table.level_up_blind()
table.level_up_ante()

print(table.get_table_status())       # TableStatus.RECRUITING (SHOWDOWN/WAITING中)
```

## テスト

```bash
pytest
```

- `tests/unit/`: `Deck` / `Chips` / `Card` / `HandEvaluator` / ゲーム進行 / テーブルのライフサイクル(レベル管理・クローズ)の単体テスト
- `tests/scenarios/`: `PokerTable` を通した一連のハンド進行のシナリオテスト
