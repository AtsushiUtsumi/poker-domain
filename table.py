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
        timeout_seconds: int = 30,
    ) -> None:
        self._table_id = table_id
        self._max_players = max_players
        self._small_blind = Chips(small_blind)
        self._big_blind = Chips(big_blind)
        self._timeout_seconds = timeout_seconds

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

    # ─── プレイヤー管理 ───

    def add_player(self, player_id: str, chips: Chips) -> GameEvent:
        if len(self._players) >= self._max_players:
            raise TableFullError("テーブルが満席です")
        if self._phase not in (GamePhase.WAITING, GamePhase.SHOWDOWN):
            raise GameAlreadyStartedError("ゲーム進行中にはプレイヤーを追加できません")
        if any(p.player_id == player_id for p in self._players):
            raise InvalidPlayerError(f"{player_id} は既に参加しています")

        self._players.append(Player(player_id=player_id, chips=chips))
        return GameEvent(
            event_type=EventType.PLAYER_JOINED,
            payload={"player_id": player_id},
        )

    def remove_player(self, player_id: str) -> GameEvent:
        if self._phase not in (GamePhase.WAITING, GamePhase.SHOWDOWN):
            raise GameAlreadyStartedError("ゲーム進行中には離開できません")
        self._players = [p for p in self._players if p.player_id != player_id]
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
        if self._phase not in (GamePhase.WAITING, GamePhase.SHOWDOWN):
            raise GameAlreadyStartedError("ゲームは進行中です")

        events: list[GameEvent] = []

        # ── 前ハンド終了後の後片付け ──
        if self._phase == GamePhase.SHOWDOWN:
            self._dealer_index = (self._dealer_index + 1) % len(self._players)
            # チップが0のプレイヤーは除外
            self._players = [p for p in self._players if p.chips.amount > 0]

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
                diff = self._current_bet.amount - player.current_bet.amount
                if player.chips.amount < diff:
                    raise InsufficientChipsError("チップ不足です")
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
                diff = self._current_bet.amount - player.current_bet.amount
                player.chips = Chips(player.chips.amount - diff)
                player.current_bet = self._current_bet
                self._pot = self._pot + Chips(diff)
                self._players_to_act.discard(self._current_player_index)
                if player.chips.amount == 0:
                    player.is_all_in = True

            case Bet(amount=amount):
                player.chips = Chips(player.chips.amount - amount)
                player.current_bet = Chips(amount)
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
        self._pot = self._pot + Chips(amount)
        if player.chips.amount == 0:
            player.is_all_in = True

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
        """全員フォールドで勝ち"""
        winner.chips = winner.chips + self._pot
        self._pot = Chips(0)
        self._phase = GamePhase.SHOWDOWN
        events.append(GameEvent(
            event_type=EventType.SHOWDOWN,
            payload={"winner_id": winner.player_id, "hands": {}},
        ))
        return ActionResult(
            state=self._snapshot(),
            events=tuple(events),
            waiting_for=None,
        )

    def _showdown(self, events: list[GameEvent]) -> ActionResult:
        """RIVER後のショーダウン"""
        self._phase = GamePhase.SHOWDOWN
        in_hand = self._get_in_hand_players()

        best_player: Player | None = None
        best_hand = None
        hands_log: dict[str, object] = {}

        for player in in_hand:
            all_cards = player.hole_cards + self._community_cards
            hand = HandEvaluator.evaluate(all_cards)
            hands_log[player.player_id] = hand
            if best_hand is None or HandEvaluator.compare(hand, best_hand) > 0:
                best_hand = hand
                best_player = player

        # TODO: スプリットポット (同じ強さの場合) は未対応
        best_player.chips = best_player.chips + self._pot  # type: ignore
        self._pot = Chips(0)

        events.append(GameEvent(
            event_type=EventType.SHOWDOWN,
            payload={"winner_id": best_player.player_id, "hands": hands_log},  # type: ignore
        ))
        return ActionResult(
            state=self._snapshot(),
            events=tuple(events),
            waiting_for=None,
        )

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
