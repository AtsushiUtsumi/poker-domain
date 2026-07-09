from poker_domain.interfaces import PokerTableInterface
from poker_domain.value_objects.action import Action, Fold, Check, Call, Bet, Raise
from poker_domain.value_objects.card import Card
from poker_domain.value_objects.chips import Chips
from poker_domain.game_state import (
    GamePhase,
    GameEvent,
    EventType,
    GameState,
    ActionResult,
    WaitingFor,
    PlayerState,
    TableStatus,
    Pot,
)
from poker_domain.player import Player
from poker_domain.deck import Deck
from poker_domain.hand_evaluator import HandEvaluator
from poker_domain.exceptions import (
    InvalidActionError,
    InsufficientChipsError,
    InvalidPlayerError,
    TableFullError,
    NotEnoughPlayersError,
    GameAlreadyStartedError,
    TableClosedError,
    RebuyNotAllowedError,
    InvalidBuyInError,
)


class PokerTable(PokerTableInterface):
    """
    テーブルの集約ルート。
    全ゲームロジックはここに閉じる。
    """

    def __init__(
        self,
        table_id: str,
        max_players: int = 6,
        small_blind: int = 25,
        big_blind: int = 50,
        ante: int = 0,
        timeout_seconds: int = 30,
        level_schedule: list[tuple[int, int, int]] | None = None,
        rake_percent: float = 0.0,
        rake_cap: int | None = None,
        rake_min_pot: int | None = None,
        allow_rebuy: bool = True,
        fixed_buy_in: int | None = None,
    ) -> None:
        self._table_id = table_id
        self._max_players = max_players
        self._timeout_seconds = timeout_seconds

        # リバイ設定: False の場合、一度バスト(チップ0で除外)したプレイヤーは再参加できない
        self._allow_rebuy = allow_rebuy
        self._busted_player_ids: set[str] = set()

        # 固定バイイン額: 設定時はこの額ピッタリのバイインのみ許可する。未指定時はバイイン額自由
        self._fixed_buy_in = fixed_buy_in

        # レーキ設定 (ショーダウンで決着したポットにのみ適用。不戦勝には適用しない)
        self._rake_percent = rake_percent
        self._rake_cap = rake_cap
        self._rake_min_pot = rake_min_pot

        # レベルスケジュール: [(small_blind, big_blind, ante), ...]。未指定時は固定額の単一レベル
        self._level_schedule: list[tuple[int, int, int]] = level_schedule or [(small_blind, big_blind, ante)]
        self._level: int = 0
        self._small_blind = Chips(self._level_schedule[0][0])
        self._big_blind = Chips(self._level_schedule[0][1])
        self._ante = Chips(self._level_schedule[0][2])

        self._players: list[Player] = []
        self._phase: GamePhase = GamePhase.WAITING
        self._deck: Deck = Deck()
        self._pot: Chips = Chips(0)
        self._current_bet: Chips = Chips(0)
        self._community_cards: tuple[Card, ...] = ()
        self._dealer_index: int = 0
        self._current_player_index: int = 0

        # 現在のラウンドでまだアクション未済のプレイヤーインデックス
        self._players_to_act: set[int] = set()

        # テーブルのライフサイクル管理
        self._closed: bool = False
        self._has_had_players: bool = False

    # ─── プレイヤー管理 ───

    def add_player(self, player_id: str, chips: Chips) -> GameEvent:
        if self._closed:
            raise TableClosedError("テーブルはクローズしています")
        if len(self._players) >= self._max_players:
            raise TableFullError("テーブルが満席です")
        if self._phase not in (GamePhase.WAITING, GamePhase.SHOWDOWN):
            raise GameAlreadyStartedError("ゲーム進行中にはプレイヤーを追加できません")
        if any(p.player_id == player_id for p in self._players):
            raise InvalidPlayerError(f"{player_id} は既に参加しています")
        if not self._allow_rebuy and player_id in self._busted_player_ids:
            raise RebuyNotAllowedError(f"{player_id} はバスト済みのためリバイ禁止テーブルに再参加できません")
        if self._fixed_buy_in is not None and chips.amount != self._fixed_buy_in:
            raise InvalidBuyInError(f"バイインは {self._fixed_buy_in} 固定です")

        self._players.append(Player(player_id=player_id, chips=chips))
        self._has_had_players = True
        return GameEvent(
            event_type=EventType.PLAYER_JOINED,
            payload={"player_id": player_id},
        )

    def remove_player(self, player_id: str) -> GameEvent:
        if self._phase not in (GamePhase.WAITING, GamePhase.SHOWDOWN):
            raise GameAlreadyStartedError("ゲーム進行中には離開できません")

        # 除外前に現在のカレントプレイヤー/ディーラーをオブジェクトとして覚えておき、
        # 縮小後のリストに対してインデックスを引き直す (該当者自身が離脱した場合は 0 にフォールバック)
        current_player = self._players[self._current_player_index] if self._players else None
        dealer_player = self._players[self._dealer_index] if self._players else None

        self._players = [p for p in self._players if p.player_id != player_id]
        # 一度でもプレイヤーがいた卓が誰もいなくなった場合はクローズ
        if self._has_had_players and len(self._players) == 0:
            self._closed = True

        if self._players:
            self._current_player_index = (
                self._players.index(current_player) if current_player in self._players else 0
            )
            self._dealer_index = (
                self._players.index(dealer_player) if dealer_player in self._players else 0
            )
        else:
            self._current_player_index = 0
            self._dealer_index = 0

        return GameEvent(
            event_type=EventType.PLAYER_LEFT,
            payload={"player_id": player_id},
        )

    # ─── ゲーム開始 ───

    def start_game(self) -> ActionResult:
        """
        ハンドを開始する。
        WAITING: 初回開始
        SHOWDOWN: 前のハンド終了後 → ディーラーを回してから次のハンド開始
        """
        if self._closed:
            raise TableClosedError("テーブルはクローズしています")
        if self._phase not in (GamePhase.WAITING, GamePhase.SHOWDOWN):
            raise GameAlreadyStartedError("ゲームは進行中です")

        events: list[GameEvent] = []

        # ── 前ハンド終了後の後片付け ──
        if self._phase == GamePhase.SHOWDOWN:
            n = len(self._players)
            # 現ディーラーの次の座席から順に、チップが残っている最初のプレイヤーを次のディーラーにする
            seating_order = [self._players[(self._dealer_index + 1 + i) % n] for i in range(n)]
            next_dealer = next((p for p in seating_order if p.chips.amount > 0), None)

            # チップが0のプレイヤーは除外 (バスト判定自体はハンド決着時に即時記録済み)
            self._players = [p for p in self._players if p.chips.amount > 0]

            if next_dealer is not None:
                self._dealer_index = self._players.index(next_dealer)

        if len(self._players) < 2:
            raise NotEnoughPlayersError("2人以上必要です")

        # ── 新ハンドの初期化 ──
        for p in self._players:
            p.reset_for_new_hand()

        self._deck = Deck()
        self._deck.shuffle()
        self._pot = Chips(0)
        self._current_bet = Chips(0)
        self._community_cards = ()

        # ── アンティ徴収 ──
        self._collect_antes(events)

        # ── ブラインド徴収 ──
        self._collect_blinds(events)

        # ── ホールカード配布 ──
        self._deal_hole_cards()

        # ── フェーズ開始 ──
        self._phase = GamePhase.PRE_FLOP
        events.append(GameEvent(event_type=EventType.GAME_STARTED, payload={}))
        events.append(GameEvent(event_type=EventType.HAND_DEALT, payload={}))

        # ── 開始プレイヤー決定 ──
        # PRE_FLOP: BB の次から開始 (heads-up では dealer=SB が先)
        if len(self._players) == 2:
            self._current_player_index = self._dealer_index
        else:
            self._current_player_index = (self._dealer_index + 3) % len(self._players)

        # PRE_FLOP では BB も to_act に含む (BBオプション)
        self._players_to_act = {
            i for i, p in enumerate(self._players) if p.is_active
        }

        events.append(GameEvent(
            event_type=EventType.TURN_CHANGED,
            payload={"player_id": self._players[self._current_player_index].player_id},
        ))

        return ActionResult(
            state=self._snapshot(),
            events=tuple(events),
            waiting_for=self._build_waiting_for(),
        )

    # ─── アクション ───

    def action(self, player_id: str, action: Action) -> ActionResult:
        if self._phase in (GamePhase.WAITING, GamePhase.SHOWDOWN):
            raise InvalidActionError("ゲームが進行中ではありません")

        player = self._get_current_player(player_id)

        self._validate_action(player, action)
        self._apply_action(player, action)

        events: list[GameEvent] = [
            GameEvent(
                event_type=EventType.PLAYER_ACTED,
                payload={"player_id": player_id},
            )
        ]

        # ── 全員フォールド以外1人 → 勝ち ──
        in_hand = self._get_in_hand_players()
        if len(in_hand) == 1:
            return self._finish_as_winner(in_hand[0], events)

        # ── ラウンド終了チェック ──
        if not self._players_to_act:
            events.append(GameEvent(event_type=EventType.ROUND_ENDED, payload={}))

            # 全員 all-in の場合は残りのコミュニティカードを一気に配る
            active = [p for p in self._players if p.is_active]
            if len(active) == 0:
                return self._run_out_remaining(events)

            if self._phase == GamePhase.RIVER:
                return self._showdown(events)
            else:
                self._advance_phase(events)
        else:
            # ターンを次へ
            self._advance_turn()
            events.append(GameEvent(
                event_type=EventType.TURN_CHANGED,
                payload={"player_id": self._players[self._current_player_index].player_id},
            ))

        return ActionResult(
            state=self._snapshot(),
            events=tuple(events),
            waiting_for=self._build_waiting_for(),
        )

    # ─── ステート取得 ───

    def get_state(self, viewer_player_id: str | None = None) -> GameState:
        return self._snapshot(viewer_player_id)

    def get_table_status(self) -> TableStatus:
        if self._closed:
            return TableStatus.CLOSED
        if self._phase in (GamePhase.WAITING, GamePhase.SHOWDOWN):
            return TableStatus.RECRUITING
        if self._phase in (GamePhase.PRE_FLOP, GamePhase.FLOP, GamePhase.TURN, GamePhase.RIVER):
            return TableStatus.PLAYING
        return TableStatus.OTHER

    # ═══════════════════════════════════════════════
    # 以下は内部メソッド
    # ═══════════════════════════════════════════════

    # ── バリデーション ──

    def _validate_action(self, player: Player, action: Action) -> None:
        match action:
            case Fold():
                pass  # いつでも可能
            case Check():
                if player.current_bet < self._current_bet:
                    raise InvalidActionError("ベット額が足りません。コールが必要です")
            case Call():
                pass  # チップが足りない場合は保有額全額でのオールインコールとして成立させる
            case Bet(amount=amount):
                if self._current_bet.amount > 0:
                    raise InvalidActionError("既にベットがある場合は Raise を使ってください")
                if amount < self._big_blind.amount:
                    raise InvalidActionError(f"最小ベットは {self._big_blind.amount} です")
                if amount > player.chips.amount:
                    raise InsufficientChipsError("チップ不足です")
            case Raise(amount=amount):
                min_raise = self._current_bet.amount * 2
                if amount < min_raise:
                    raise InvalidActionError(f"最小レイズは {min_raise} です")
                diff = amount - player.current_bet.amount
                if diff > player.chips.amount:
                    raise InsufficientChipsError("チップ不足です")

    # ── 適用 ──

    def _apply_action(self, player: Player, action: Action) -> None:
        match action:
            case Fold():
                player.folded = True
                self._players_to_act.discard(self._current_player_index)

            case Check():
                self._players_to_act.discard(self._current_player_index)

            case Call():
                # 不足していれば保有チップ全額でのオールインコールとする (サイドポットの発生源)
                diff = min(
                    self._current_bet.amount - player.current_bet.amount,
                    player.chips.amount,
                )
                player.chips = Chips(player.chips.amount - diff)
                player.current_bet = player.current_bet + Chips(diff)
                player.total_contributed = player.total_contributed + Chips(diff)
                self._pot = self._pot + Chips(diff)
                self._players_to_act.discard(self._current_player_index)
                if player.chips.amount == 0:
                    player.is_all_in = True

            case Bet(amount=amount):
                player.chips = Chips(player.chips.amount - amount)
                player.current_bet = Chips(amount)
                player.total_contributed = player.total_contributed + Chips(amount)
                self._current_bet = Chips(amount)
                self._pot = self._pot + Chips(amount)
                if player.chips.amount == 0:
                    player.is_all_in = True
                # Bet → 他の全アクティブプレイヤーを to_act に戻す
                self._players_to_act = {
                    i for i, p in enumerate(self._players)
                    if p.is_active and i != self._current_player_index
                }

            case Raise(amount=amount):
                diff = amount - player.current_bet.amount
                player.chips = Chips(player.chips.amount - diff)
                player.current_bet = Chips(amount)
                player.total_contributed = player.total_contributed + Chips(diff)
                self._current_bet = Chips(amount)
                self._pot = self._pot + Chips(diff)
                if player.chips.amount == 0:
                    player.is_all_in = True
                # Raise → 他の全アクティブプレイヤーを to_act に戻す
                self._players_to_act = {
                    i for i, p in enumerate(self._players)
                    if p.is_active and i != self._current_player_index
                }

    # ── ブラインド徴収 ──

    def _collect_blinds(self, events: list[GameEvent]) -> None:
        n = len(self._players)
        if n == 2:
            sb_index = self._dealer_index
            bb_index = (self._dealer_index + 1) % n
        else:
            sb_index = (self._dealer_index + 1) % n
            bb_index = (self._dealer_index + 2) % n

        self._pay_blind(sb_index, self._small_blind)
        self._pay_blind(bb_index, self._big_blind)
        self._current_bet = self._big_blind  # 現時点のベット額 = BB

    def _pay_blind(self, player_index: int, blind: Chips) -> None:
        player = self._players[player_index]
        amount = min(blind.amount, player.chips.amount)
        player.chips = Chips(player.chips.amount - amount)
        player.current_bet = Chips(amount)
        player.total_contributed = player.total_contributed + Chips(amount)
        self._pot = self._pot + Chips(amount)
        if player.chips.amount == 0:
            player.is_all_in = True

    # ── アンティ徴収 ──

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

    # ── レベル ──

    def level_up(self) -> GameEvent:
        if self._level < len(self._level_schedule) - 1:
            self._level += 1
            sb, bb, ante = self._level_schedule[self._level]
            self._small_blind = Chips(sb)
            self._big_blind = Chips(bb)
            self._ante = Chips(ante)
        return GameEvent(
            event_type=EventType.LEVEL_UP,
            payload={
                "level": self._level,
                "small_blind": self._small_blind.amount,
                "big_blind": self._big_blind.amount,
                "ante": self._ante.amount,
            },
        )

    # ── ホールカード配布 ──

    def _deal_hole_cards(self) -> None:
        """1枚ずつ2回配る"""
        for _ in range(2):
            for i in range(len(self._players)):
                idx = (self._dealer_index + 1 + i) % len(self._players)
                player = self._players[idx]
                if player.is_in_hand:
                    player.hole_cards = player.hole_cards + self._deck.deal(1)

    # ── フェーズ遷移 ──

    def _advance_phase(self, events: list[GameEvent]) -> None:
        next_phase = {
            GamePhase.PRE_FLOP: GamePhase.FLOP,
            GamePhase.FLOP: GamePhase.TURN,
            GamePhase.TURN: GamePhase.RIVER,
        }
        self._phase = next_phase[self._phase]

        # コミュニティカード配布
        match self._phase:
            case GamePhase.FLOP:
                self._community_cards = self._community_cards + self._deck.deal(3)
            case GamePhase.TURN | GamePhase.RIVER:
                self._community_cards = self._community_cards + self._deck.deal(1)

        events.append(GameEvent(
            event_type=EventType.COMMUNITY_DEALT,
            payload={"community_cards": self._community_cards},
        ))

        # ラウンドリセット
        self._current_bet = Chips(0)
        for p in self._players:
            if p.is_in_hand:
                p.current_bet = Chips(0)

        # to_act: アクティブ全員 (all-in は除外)
        self._players_to_act = {
            i for i, p in enumerate(self._players) if p.is_active
        }

        # ターン: ディーラーの次のアクティブプレイヤーから
        self._current_player_index = self._next_active_index(self._dealer_index)
        events.append(GameEvent(
            event_type=EventType.TURN_CHANGED,
            payload={"player_id": self._players[self._current_player_index].player_id},
        ))

    # ── 全員 all-in の場合: 残りのコミュニティカードを一気に配る ──

    def _run_out_remaining(self, events: list[GameEvent]) -> ActionResult:
        while self._phase != GamePhase.RIVER:
            next_phase = {
                GamePhase.PRE_FLOP: GamePhase.FLOP,
                GamePhase.FLOP: GamePhase.TURN,
                GamePhase.TURN: GamePhase.RIVER,
            }
            self._phase = next_phase[self._phase]
            match self._phase:
                case GamePhase.FLOP:
                    self._community_cards = self._community_cards + self._deck.deal(3)
                case GamePhase.TURN | GamePhase.RIVER:
                    self._community_cards = self._community_cards + self._deck.deal(1)
            events.append(GameEvent(
                event_type=EventType.COMMUNITY_DEALT,
                payload={"community_cards": self._community_cards},
            ))

        return self._showdown(events)

    # ── ターン進行 ──

    def _advance_turn(self) -> None:
        self._current_player_index = self._next_active_index(self._current_player_index)

    def _next_active_index(self, from_index: int) -> int:
        """from_index の次のアクティブプレイヤーのインデックス"""
        n = len(self._players)
        i = (from_index + 1) % n
        while i != from_index:
            if self._players[i].is_active:
                return i
            i = (i + 1) % n
        return from_index  # アクティブが1人だけ

    # ── 勝敗 ──

    def _finish_as_winner(self, winner: Player, events: list[GameEvent]) -> ActionResult:
        """全員フォールドで不戦勝。サイドポットの偏りに関わらず残ったポット全額を獲得し、レーキは取らない"""
        payout = self._pot
        winner.chips = winner.chips + payout
        self._pot = Chips(0)
        self._reset_contributions()
        self._phase = GamePhase.SHOWDOWN
        self._record_busted_players()
        events.append(GameEvent(
            event_type=EventType.SHOWDOWN,
            payload={
                "winner_id": winner.player_id,
                "hands": {},
                "payouts": {winner.player_id: payout.amount},
                "rake": 0,
            },
        ))
        self._close_if_finished(events)
        return ActionResult(
            state=self._snapshot(),
            events=tuple(events),
            waiting_for=None,
        )

    def _showdown(self, events: list[GameEvent]) -> ActionResult:
        """RIVER後のショーダウン。サイドポットごとに勝者を判定して分配し、レーキを控除する"""
        self._phase = GamePhase.SHOWDOWN
        in_hand = self._get_in_hand_players()

        hands_log: dict[str, object] = {
            player.player_id: HandEvaluator.evaluate(player.hole_cards + self._community_cards)
            for player in in_hand
        }

        raw_pots = self._compute_pots()
        pots, rake = self._apply_rake(raw_pots)

        payouts: dict[str, int] = {}
        for pot in pots:
            for player_id, amount in self._distribute_pot(pot, hands_log).items():
                payouts[player_id] = payouts.get(player_id, 0) + amount

        for player in self._players:
            won = payouts.get(player.player_id, 0)
            if won:
                player.chips = player.chips + Chips(won)

        self._pot = Chips(0)
        self._reset_contributions()
        self._record_busted_players()

        winner_id = max(payouts, key=payouts.get) if payouts else None
        events.append(GameEvent(
            event_type=EventType.SHOWDOWN,
            payload={
                "winner_id": winner_id,
                "hands": hands_log,
                "pots": pots,
                "payouts": payouts,
                "rake": rake,
            },
        ))
        self._close_if_finished(events)
        return ActionResult(
            state=self._snapshot(),
            events=tuple(events),
            waiting_for=None,
        )

    # ── サイドポット計算 ──

    def _compute_pots(self) -> tuple[Pot, ...]:
        """各プレイヤーの累計拠出額からメインポット/サイドポットを算出する"""
        contributions = [
            (p, p.total_contributed.amount) for p in self._players if p.total_contributed.amount > 0
        ]
        if not contributions:
            return ()

        levels = sorted({amount for _, amount in contributions})
        pots: list[Pot] = []
        prev_level = 0
        for level in levels:
            tier = level - prev_level
            prev_level = level
            if tier <= 0:
                continue
            contributors = [p for p, amount in contributions if amount >= level]
            eligible = tuple(p.player_id for p in contributors if not p.folded)
            pots.append(Pot(amount=Chips(tier * len(contributors)), eligible_player_ids=eligible))
        return tuple(pots)

    def _distribute_pot(self, pot: Pot, hands: dict[str, object]) -> dict[str, int]:
        """1つのポットについて、対象者内で最強のハンドに (同点なら等分で) 配る"""
        eligible = [p for p in self._players if p.player_id in pot.eligible_player_ids]
        if not eligible:
            return {}

        best_hand = None
        winners: list[Player] = []
        for player in eligible:
            hand = hands[player.player_id]
            if best_hand is None:
                best_hand, winners = hand, [player]
                continue
            cmp = HandEvaluator.compare(hand, best_hand)  # type: ignore[arg-type]
            if cmp > 0:
                best_hand, winners = hand, [player]
            elif cmp == 0:
                winners.append(player)

        share, remainder = divmod(pot.amount.amount, len(winners))
        payouts = {p.player_id: share for p in winners}
        if remainder:
            # 端数チップはディーラーの次の座席から順に、勝者の間で1枚ずつ配る
            ordered = self._order_from_dealer(winners)
            for i in range(remainder):
                winner_id = ordered[i % len(ordered)].player_id
                payouts[winner_id] += 1
        return payouts

    def _order_from_dealer(self, players: list[Player]) -> list[Player]:
        """ディーラーの次の座席から時計回りの順に並べ替える"""
        n = len(self._players)
        seat_index = {id(p): i for i, p in enumerate(self._players)}

        def seat_distance(p: Player) -> int:
            return (seat_index[id(p)] - self._dealer_index - 1) % n

        return sorted(players, key=seat_distance)

    # ── レーキ ──

    def _calculate_rake(self, pot_amount: int) -> int:
        if pot_amount <= 0 or self._rake_percent <= 0:
            return 0
        if self._rake_min_pot is not None and pot_amount < self._rake_min_pot:
            return 0
        rake = int(pot_amount * self._rake_percent)
        if self._rake_cap is not None:
            rake = min(rake, self._rake_cap)
        return rake

    def _apply_rake(self, pots: tuple[Pot, ...]) -> tuple[tuple[Pot, ...], int]:
        """合計ポットに対してレーキを計算し、メインポット(先頭)から差し引く"""
        if not pots:
            return pots, 0
        total = sum(p.amount.amount for p in pots)
        rake = self._calculate_rake(total)
        if rake <= 0:
            return pots, 0

        main_pot = pots[0]
        deduction = min(rake, main_pot.amount.amount)
        adjusted_main = Pot(
            amount=Chips(main_pot.amount.amount - deduction),
            eligible_player_ids=main_pot.eligible_player_ids,
        )
        return (adjusted_main,) + pots[1:], deduction

    def _reset_contributions(self) -> None:
        for p in self._players:
            p.total_contributed = Chips(0)

    def _record_busted_players(self) -> None:
        """チップ0が確定した時点で即座にバスト済みとして記録する (リバイ禁止判定用)"""
        self._busted_player_ids |= {p.player_id for p in self._players if p.chips.amount == 0}

    # ── ハンド終了後のクローズ判定 ──

    def _close_if_finished(self, events: list[GameEvent]) -> None:
        """生存 (チップ>0) プレイヤーが1人以下になったら卓をクローズする"""
        survivors = [p for p in self._players if p.chips.amount > 0]
        if len(survivors) <= 1 and not self._closed:
            self._closed = True
            events.append(GameEvent(event_type=EventType.TABLE_CLOSED, payload={}))

    # ── ヘルパー ──

    def _get_current_player(self, player_id: str) -> Player:
        current = self._players[self._current_player_index]
        if current.player_id != player_id:
            raise InvalidPlayerError(
                f"現在のターンは {current.player_id} です。{player_id} ではありません"
            )
        return current

    def _get_in_hand_players(self) -> list[Player]:
        """フォールドしていない全プレイヤー (all-in も含む)"""
        return [p for p in self._players if p.is_in_hand]

    # ── スナップショット ──

    def _snapshot(self, viewer_player_id: str | None = None) -> GameState:
        player_states = []
        for p in self._players:
            # SHOWDOWN では全員のカードを公開; それ以外は viewer のみ
            show_cards = (
                self._phase == GamePhase.SHOWDOWN
                or p.player_id == viewer_player_id
            )
            player_states.append(PlayerState(
                player_id=p.player_id,
                chips=p.chips,
                current_bet=p.current_bet,
                folded=p.folded,
                is_all_in=p.is_all_in,
                hole_cards=p.hole_cards if show_cards else None,
            ))

        current_id: str | None = None
        if self._players:
            current_id = self._players[self._current_player_index].player_id

        dealer_id: str = ""
        if self._players:
            dealer_id = self._players[self._dealer_index].player_id

        return GameState(
            table_id=self._table_id,
            phase=self._phase,
            pot=self._pot,
            current_bet=self._current_bet,
            community_cards=self._community_cards,
            players=tuple(player_states),
            current_player_id=current_id,
            dealer_id=dealer_id,
            small_blind=self._small_blind,
            big_blind=self._big_blind,
            ante=self._ante,
            level=self._level,
            status=self.get_table_status(),
            side_pots=self._compute_pots(),
            rake_percent=self._rake_percent,
            rake_cap=self._rake_cap,
            rake_min_pot=self._rake_min_pot,
        )

    # ── WaitingFor 生成 ──

    def _build_waiting_for(self) -> WaitingFor | None:
        if not self._players_to_act:
            return None
        current = self._players[self._current_player_index]
        return WaitingFor(
            player_id=current.player_id,
            valid_actions=self._get_valid_actions(current),
            timeout_seconds=self._timeout_seconds,
        )

    def _get_valid_actions(self, player: Player) -> tuple[type, ...]:
        actions: list[type] = [Fold]
        if player.current_bet == self._current_bet:
            actions.append(Check)
        else:
            actions.append(Call)
        if self._current_bet.amount == 0:
            actions.append(Bet)
        else:
            actions.append(Raise)
        return tuple(actions)
