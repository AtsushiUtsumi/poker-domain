# poker_domain: アンティがcurrent_betに混入してゲームが停止するバグの修正依頼

## 背景・目的

`3d16858 チップ拠出処理をPlayer.contribute()に集約` のリファクタ以降、アンティ
(ante)が有効なテーブルで、まれにハンド進行が完全に停止する不具合が
mullhouse側の実運用で発生した(`docker logs mullhouse-backend` に
`ValueError: チップは負にはなれません` が未処理例外として記録され、
それ以降そのテーブルは誰の手番も進まなくなる)。

原因を `PokerTable._apply_action` の `Call()` 分岐まで追い、ante>0 の条件で
`PokerTable` を直接操作するスタンドアロンのシミュレーションスクリプトで
即座に再現できることを確認した(seed固定でヘッズアップ〜6人卓・複数ハンド
実行し、初回クラッシュまで数手)。

mullhouse側では暫定的に「本来 call を提示すべきでない局面で call を提示
しない」よう手番判定ロジックにガード(`current_bet.amount >= state.current_bet.amount`
なら call ではなく check を提示)を追加してクラッシュ自体は回避したが、
これは症状を隠すパッチであり、根本原因は `poker_domain` 側の状態不整合な
ので、そちらでの修正をお願いしたい。

## 依頼内容

### 根本原因

`Player.contribute()` (`src/poker_domain/player.py`) は「チップ減算 →
`current_bet` 加算 → `total_contributed` 加算 → all-in判定」の5行を共通化
したものだが、この中の `current_bet` 加算は**ブラインド/コール/ベット/レイズ
専用の意味**であり、**アンティには当てはまらない**。

```python
def contribute(self, amount: int) -> int:
    paid = min(amount, self.chips.amount)
    self.chips = Chips(self.chips.amount - paid)
    self.current_bet = self.current_bet + Chips(paid)   # ← アンティでは不適切
    self.total_contributed = self.total_contributed + Chips(paid)
    if self.chips.amount == 0:
        self.is_all_in = True
    return paid
```

`PokerTable._collect_antes` (`src/poker_domain/table.py`) がこの
`contribute()` をそのまま呼んでいるため、アンティ徴収の時点で全プレイヤーの
`current_bet` が `ante` 分だけ底上げされた状態でハンドが始まる:

```python
def _collect_antes(self, events: list[GameEvent]) -> None:
    if self._ante.amount <= 0:
        return
    for player in self._players:
        paid = player.contribute(self._ante.amount)   # current_bet が ante 分増える
        self._pot = self._pot + Chips(paid)
```

一方、テーブル全体の基準となる `self._current_bet` は `_collect_blinds` の
最後で「ビッグブラインドの額そのもの」に固定されるだけで、アンティは
一切考慮されない:

```python
def _collect_blinds(self, events: list[GameEvent]) -> None:
    ...
    self._pay_blind(sb_index, self._small_blind)
    self._pay_blind(bb_index, self._big_blind)
    self._current_bet = self._big_blind  # ← ante を含まない
```

結果、例えば `ante=5, big_blind=50` のテーブルでBBを務めるプレイヤーは
`current_bet = 5(ante) + 50(BB) = 55` になるが、テーブル側の
`self._current_bet` は `50` のまま。誰も再レイズせずアクションがBBまで
戻ってくると、BBは本来「チェックでよい」局面のはずが、
`player.current_bet(55) != self._current_bet(50)` という不一致だけを見て
コールを促されうる状態になる。そのままコールが適用されると:

```python
case Call():
    diff = self._current_bet.amount - player.current_bet.amount  # 50 - 55 = -5
    paid = player._contribute(diff)   # Chips(-5) → ValueError
```

`_validate_action` の `Call()` 分岐は「チップが足りない場合は保有額全額での
オールインコールとして成立させる」という理由で一切のバリデーションをして
いない(`pass` のみ)ため、この不整合な状態でも例外なく `_apply_action` まで
到達してしまう。

修正前(旧 `_collect_antes` 実装、`3d16858` の親コミット)は `current_bet` を
一切触っていなかった:

```python
def _collect_antes(self, events: list[GameEvent]) -> None:
    if self._ante.amount <= 0:
        return
    for player in self._players:
        amount = min(self._ante.amount, player.chips.amount)
        player.chips = Chips(player.chips.amount - amount)
        player.total_contributed = player.total_contributed + Chips(amount)
        self._pot = self._pot + Chips(amount)
        if player.chips.amount == 0:
            player.is_all_in = True
```

### 修正案

以下のいずれかで、アンティ拠出時に `current_bet` を変化させないようにして
ほしい。

- **案A(推奨)**: `Player.contribute()` に `affects_current_bet: bool = True`
  のような引数を追加し、`_collect_antes` からの呼び出しだけ
  `affects_current_bet=False` で呼ぶ。
  ```python
  def contribute(self, amount: int, *, affects_current_bet: bool = True) -> int:
      paid = min(amount, self.chips.amount)
      self.chips = Chips(self.chips.amount - paid)
      if affects_current_bet:
          self.current_bet = self.current_bet + Chips(paid)
      self.total_contributed = self.total_contributed + Chips(paid)
      if self.chips.amount == 0:
          self.is_all_in = True
      return paid
  ```
  ```python
  def _collect_antes(self, events: list[GameEvent]) -> None:
      if self._ante.amount <= 0:
          return
      for player in self._players:
          paid = player.contribute(self._ante.amount, affects_current_bet=False)
          self._pot = self._pot + Chips(paid)
  ```

- **案B**: `_collect_antes` だけ `contribute()` を使わず、チップ減算・
  `total_contributed`加算・all-in判定を個別に書き戻す(リファクタ前の実装に
  戻す)。共通化のメリットは薄れるが、変更範囲は最小になる。

どちらでも構わないが、**アンティ徴収後に全プレイヤーの `current_bet` が
`0` のままであること**、および**その後の `_collect_blinds` で計算される
`self._current_bet` と、ブラインドを払ったプレイヤーの `current_bet` が
一致すること**を保証してほしい。

### あわせて検討してほしいこと(任意)

`_validate_action` の `Call()` 分岐(`pass # チップが足りない場合は保有額
全額でのオールインコールとして成立させる`)は、`diff` が負になるケースを
一切弾いていない。上記の根本修正が入れば理論上は起きなくなるはずだが、
最後の防衛線として

```python
case Call():
    if player.current_bet.amount > self._current_bet.amount:
        raise InvalidActionError("既に必要額以上を拠出済みです")
```

のようなガードを入れておくと、将来同種の状態不整合が再発してもクラッシュ
ではなく `InvalidActionError`(呼び出し側で捕捉・フォールバック可能)に
落ちるようになり、堅牢性が上がると思う。必須ではないので判断はお任せする。

## 対象外(今回は不要)

- アンティのレベルアップ・スケジュール機構自体の変更(既存の
  `level_schedule` の仕組みはそのままでよい)
- サイドポット計算ロジックの変更(今回の不具合はサイドポットとは無関係)

## 影響範囲

- `src/poker_domain/player.py`: `Player.contribute()` (案Aの場合)
- `src/poker_domain/table.py`: `PokerTable._collect_antes()`
- 既存のユニットテスト(`tests/unit/test_table_lifecycle.py` 等)にアンティ
  ありのケースがあれば、`current_bet` の期待値を見直す必要があるかもしれない
- 公開API・`GameState`の形状に変更なし(内部状態の整合性修正のみ)

## mullhouse側で追って対応すること(参考・今回のスコープ外)

- 修正版 `poker_domain` を取り込み後、`backend/poker_service.py` の
  `compute_waiting_for()` に暫定で入れた
  `current.current_bet.amount >= state.current_bet.amount` ガード
  (元は `==` 比較だった)は、ante起因の不整合が解消されるため実質的に
  不要になる。ただし「call を提示すべきでない局面で call を提示しない」
  という意味では一般に安全側のロジックなので、そのまま残すか判断する
  (削除は必須ではない)。
