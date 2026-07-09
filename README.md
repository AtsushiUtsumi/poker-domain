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
    rake_percent: float = 0.0,
    rake_cap: int | None = None,
    rake_min_pot: int | None = None,
    allow_rebuy: bool = True,
    fixed_buy_in: int | None = None,
)
```

- `blind_schedule` を渡すと `[(small_blind, big_blind), ...]` のレベル表として管理される
  (未指定時は `small_blind`/`big_blind` 引数を単一レベルとして使用)
- `ante_schedule` を渡すと `[ante, ...]` のレベル表として管理される (未指定時はアンティなし = レベル0固定)
- `rake_percent` / `rake_cap` / `rake_min_pot` でレーキ(テラ銭)を設定できる。詳細は後述の「レーキ」節を参照
- `allow_rebuy=False` にすると、一度チップ0でバストして除外されたプレイヤーIDは同じテーブルに
  `add_player()` で再参加できなくなり、`RebuyNotAllowedError` になる (バスト前の離脱・再入場は対象外)
- `fixed_buy_in` を設定すると、`add_player()` の `chips` がこの額と完全に一致する場合のみ参加でき、
  一致しない場合は `InvalidBuyInError` になる (未設定時はバイイン額は自由)

| メソッド | 説明 |
|---|---|
| `add_player(player_id, chips)` | プレイヤーを着席させる。満席・進行中・重複参加・クローズ後・リバイ禁止時のバスト済みID・固定バイイン額不一致はエラー |
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

### リバイ

- `PokerTable(..., allow_rebuy=False)` で作成すると、ハンド終了時にチップ0で除外(バスト)された
  プレイヤーIDを記憶し、以後同じIDで `add_player()` を呼んでも `RebuyNotAllowedError` になる
- バストする前に自発的に `remove_player()` で離脱したプレイヤーの再入場は制限されない
  (制限対象はあくまで「チップを失って強制退席したプレイヤー」)
- 既定値は `allow_rebuy=True` で、従来通り誰でも何度でも再参加できる

### バイイン額の固定

- `PokerTable(..., fixed_buy_in=1000)` のように作成すると、`add_player()` の `chips` が
  この額とピッタリ一致する場合のみ参加を受け付け、それ以外は `InvalidBuyInError` になる
  (リバイ時の再バイインにも同じ制約が適用される)
- 既定値は `fixed_buy_in=None` で、従来通り任意の額でバイインできる

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

`Call()` は保有チップがコールに必要な額に満たない場合でも拒否されず、
**保有チップ全額でのオールインコール**として成立します(サイドポットの主な発生源)。
一方 `Bet`/`Raise` は必要額に満たない場合エラーになり、不足額でのオールインベット/レイズには対応していません
(ショートスタックが取れる不足額アクションは Call のみ)。

ラウンドが終了すると:
- 全員フォールドで1人残った場合 → その場で勝者に**そのハンドのポット全額**が渡り `SHOWDOWN` へ
  (サイドポットの構造に関わらず全額。誰も対抗できない以上、按分の必要がないため。レーキも取らない)
- 全員 all-in の場合 → 残りのコミュニティカードを一気に配ってショーダウン
- `RIVER` のラウンド終了 → ショーダウンしてポット(メイン/サイド)ごとに役を比較し分配
- それ以外 → 次のフェーズに進み、コミュニティカードを配布 (FLOP:3枚、TURN/RIVER:各1枚)

### サイドポット

各プレイヤーの「そのハンドを通じた累計拠出額」(`Player.total_contributed`、アンティ・ブラインド・各ストリートの
コール/ベット/レイズをすべて合算したもの)をもとに、拠出額の階層ごとにポットを分割します。

- 拠出額を昇順に並べた各段階で「その段階以上を拠出した全員」からその差分だけ集めたものが1つのポットになる
- 各ポットの獲得資格 (`eligible_player_ids`) は「その段階まで拠出していて、かつフォールドしていない」プレイヤーに限られる
  (フォールド済みのプレイヤーの拠出分もポットには残るが、本人は対象外になる)
- ショーダウンでは、ポットごとに対象者内で最も強い役を判定して分配する。複数人が同点の場合は等分し、
  割り切れない端数チップは**ディーラーの次の座席から時計回りの順に**1枚ずつ配る
- `GameState.side_pots` (`tuple[Pot, ...]`) でハンド進行中も含めて常時参照できる。
  `Pot` は `amount: Chips` と `eligible_player_ids: tuple[str, ...]` を持つ
- `ActionResult.events` の `SHOWDOWN` イベントの `payload` にも `pots` (分配後のポット内訳)、
  `payouts` (プレイヤーIDごとの獲得額)、`winner_id` (最大獲得額のプレイヤー、後方互換用)、`rake` が含まれる

### レーキ

- `rake_percent`: ポット合計に対するレーキ率 (例: `0.05` = 5%)
- `rake_cap`: レーキの上限額 (未指定なら上限なし)
- `rake_min_pot`: この額に満たないポットからはレーキを取らない (未指定なら閾値なし)
- レーキは**実際にショーダウンで役を比較して決着した場合にのみ**控除され、メインポットから差し引かれる
  (`_apply_rake` はサイドポットには手を付けない)
- **全員フォールドによる不戦勝(ウォークオーバー)にはレーキを取らない**

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
  `small_blind`/`big_blind`/`ante`、`blind_level`/`ante_level`、`status` (`TableStatus`)、
  `side_pots` (`tuple[Pot, ...]`)、`rake_percent`/`rake_cap`/`rake_min_pot` など)
- **`PlayerState`**: プレイヤー1人分のスナップショット。`hole_cards` は showdown時、または
  `get_state()` の `viewer_player_id` と一致する場合のみ公開される
- **`Pot`**: サイドポットの1枠。`amount: Chips` と `eligible_player_ids: tuple[str, ...]` を持つ
- **`ActionResult`**: `action()` / `start_game()` の戻り値。`state` (最新スナップショット)、
  `events` (発生したイベント列)、`waiting_for` (次に誰の・どのアクションを待っているか。ゲーム終了時は `None`)
- **`GameEvent`** / **`EventType`**: `PLAYER_JOINED` / `PLAYER_LEFT` / `GAME_STARTED` / `HAND_DEALT` /
  `PLAYER_ACTED` / `ROUND_ENDED` / `COMMUNITY_DEALT` / `TURN_CHANGED` / `SHOWDOWN` /
  `BLIND_LEVEL_UP` / `ANTE_LEVEL_UP` / `TABLE_CLOSED`
  (`SHOWDOWN` の `payload` には `hands`/`pots`/`payouts`/`winner_id`/`rake` を含む)
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
- `RebuyNotAllowedError`
- `InvalidBuyInError`

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

- `tests/unit/`: `Deck` / `Chips` / `Card` / `HandEvaluator` / ゲーム進行 /
  テーブルのライフサイクル(レベル管理・クローズ・サイドポット・レーキ)の単体テスト
- `tests/scenarios/`: `PokerTable` を通した一連のハンド進行のシナリオテスト
