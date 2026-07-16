# poker_domain: ショートスタックの先制オールインベットを許可する

## 背景・目的

`mullhouse` はポーカー卓機能のCPU対戦相手として `backend/cpu/` 配下に複数の
プレイスタイル(タイト/ルーズ/アグレッシブ/パッシブ等)のプラグインモジュールを
持っている。各CPUは手番ごとに `CPUStrategy.decide()` でアクションを決めるが、
`current_bet == 0`(誰もまだベットしていない = 自分から先制して賭ける番)の
場面で、手持ちチップがビッグブラインド(BB)未満のショートスタックだと、
現状の `PokerTable` の仕様では **合法な `Bet` が一つも存在しない** ため、
CPUはチェックするしかなく、「オールインでプッシュする」という一般的な
ショートスタック戦略を実装できない。

該当箇所は `backend/cpu/base.py` の `can_bet()`:
```python
def can_bet(ctx: CPUDecisionContext) -> bool:
    return "bet" in ctx.valid_actions and ctx.max_bet >= ctx.min_bet
```
ここで `ctx.max_bet`(= 自分の残りチップ)が `ctx.min_bet`(= BB額、
`backend/poker_service.py` の `build_cpu_context` で `min_bet=state.big_blind.amount`
としてセットしている)を下回っていると `can_bet()` は常に `False` を返し、
どのCPUモジュール(`rock.py`/`maniac.py`/`shark.py`/`balanced.py`/
`calling_station.py`)も先制ベットの選択肢自体を検討できない。

これは通常のポーカーのルールに反する。一般的なポーカーでは「最小ベット額は
BB」が原則だが、**手持ちチップ全額を賭ける場合はBB未満でも合法なオールイン**
として例外的に認められる。

## 依頼内容

`poker_domain/table.py` の `PokerTable._validate_action` にある `Bet` ケースの
バリデーションを修正し、「ベット額が手持ちチップ全額と一致する場合は、
BB未満でも合法」という例外を追加してほしい。

現状:
```python
case Bet(amount=amount):
    if self._current_bet.amount > 0:
        raise InvalidActionError("既にベットがある場合は Raise を使ってください")
    if amount < self._big_blind.amount:
        raise InvalidActionError(f"最小ベットは {self._big_blind.amount} です")
    if amount > player.chips.amount:
        raise InsufficientChipsError("チップ不足です")
```

変更案:
```python
case Bet(amount=amount):
    if self._current_bet.amount > 0:
        raise InvalidActionError("既にベットがある場合は Raise を使ってください")
    is_all_in_bet = amount == player.chips.amount
    if amount < self._big_blind.amount and not is_all_in_bet:
        raise InvalidActionError(f"最小ベットは {self._big_blind.amount} です")
    if amount > player.chips.amount:
        raise InsufficientChipsError("チップ不足です")
```

`_apply_action` 側の `Bet` 処理(`player.chips.amount == 0` になったら
`is_all_in = True` をセットする、他のアクティブプレイヤーを
`_players_to_act` に戻す、など)は現状の実装のままで、この変更後もそのまま
正しく動作するはず。変更が必要なのは `_validate_action` のガード条件のみ。

## 対象外(今回は不要)

- `Raise` 側の「最小レイズ額未満でのオールインレイズ」は今回のスコープ外。
  こちらは手持ちチップ不足で `can_raise()` が `False` になった場合、
  `Call()`(コールは常に手持ちチップ全額でキャップされてオールインとして
  成立する)に自動的にフォールバックする実装が `mullhouse` 側に既にあり、
  実用上の問題が出ていないため。
- ベットサイジングの推奨額(ポットベット/ハーフポット等)のAPI追加は不要。

## 影響範囲

- 変更ファイルは `poker_domain/table.py` の `PokerTable._validate_action` の
  `Bet` ケースのみ(数行の条件追加)。
- `_apply_action` / `GameEvent` / `GameState` などの公開データ構造・戻り値の
  形は変わらない。
- 破壊的変更ではない。従来 `InvalidActionError` になっていた
  「チップ不足で先制ベットしようとする」ケースの一部が新たに成功するように
  なるだけで、それ以外の既存の合法/非合法判定は変わらない。

## mullhouse側で追って対応すること(参考・今回のスコープ外)

- 対応後、`poker_domain` の pin を更新(`poker-domain-sync` スキル)。
- `backend/poker_service.py` の `build_cpu_context` で
  `min_bet=state.big_blind.amount` を渡しているのはそのままでよい
  (エンジン側が「全額ならBB未満でも合法」と判断してくれるため)。ただし
  `backend/cpu/base.py` の `can_bet()` はチップ不足でも「全額ベット」なら
  許可されるようにガード条件を緩め、各CPUモジュールのベット額計算でも
  「クランプ後の額がBB未満なら全額(オールイン)にする」ロジックへの
  微修正が必要になる見込み。
