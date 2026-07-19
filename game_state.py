from dataclasses import dataclass
from enum import Enum
from typing import Any

from poker_domain.value_objects.chips import Chips
from poker_domain.value_objects.action import Action
from poker_domain.value_objects.community_cards import CommunityCards
from poker_domain.value_objects.hole_cards import HoleCards


class GamePhase(Enum):
    WAITING = "waiting"       # プレイヤー待機中
    PRE_FLOP = "pre_flop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"


class TableStatus(Enum):
    """PokerTable 全体のライフサイクル状態 (GamePhase とは別軸)"""
    RECRUITING = "recruiting"  # 参加募集中 (新規ハンドの開始前 = プレイヤー参加/離脱が可能)
    PLAYING = "playing"        # プレイ中 (ハンド進行中)
    CLOSED = "closed"          # クローズ (卓が空になった、または対戦不能な人数まで減った)
    OTHER = "other"            # 上記いずれにも該当しない状態


class EventType(Enum):
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    GAME_STARTED = "game_started"
    HAND_DEALT = "hand_dealt"
    PLAYER_ACTED = "player_acted"
    ROUND_ENDED = "round_ended"
    COMMUNITY_DEALT = "community_dealt"
    TURN_CHANGED = "turn_changed"
    SHOWDOWN = "showdown"
    LEVEL_UP = "level_up"
    TABLE_CLOSED = "table_closed"


@dataclass(frozen=True)
class GameEvent:
    event_type: EventType
    payload: dict[str, Any]


@dataclass(frozen=True)
class Pot:
    """メインポット/サイドポットの1枠。参加権があるプレイヤーだけが対象になる"""
    amount: Chips
    eligible_player_ids: tuple[str, ...]


@dataclass(frozen=True)
class WaitingFor:
    """poker_domain が次に誰のアクションを待っているか"""
    player_id: str
    valid_actions: tuple[type, ...]  # e.g. (Fold, Check, Raise)
    timeout_seconds: int


@dataclass(frozen=True)
class ActionLogEntry:
    """ハンド内でプレイヤーが取ったアクション1件分の履歴"""
    player_id: str
    phase: GamePhase      # アクションを取った時点のフェーズ (PRE_FLOP/FLOP/TURN/RIVER)
    action: str           # "fold" | "check" | "call" | "bet" | "raise"
    amount: int | None    # bet/raise の場合のみ金額、それ以外は None


@dataclass(frozen=True)
class PlayerState:
    """スナップショット用のプレイヤー状態 (不変)"""
    player_id: str
    chips: Chips
    current_bet: Chips
    folded: bool
    is_all_in: bool
    hole_cards: HoleCards | None  # viewer のカードだけ見える


@dataclass(frozen=True)
class GameState:
    """テーブル全体のスナップショット (不変)"""
    table_id: str
    phase: GamePhase
    pot: Chips
    current_bet: Chips
    community_cards: CommunityCards
    players: tuple[PlayerState, ...]
    current_player_id: str | None
    dealer_id: str
    small_blind: Chips
    big_blind: Chips
    ante: Chips
    level: int
    status: TableStatus
    side_pots: tuple[Pot, ...]
    rake_percent: float
    rake_cap: int | None
    rake_min_pot: int | None
    action_log: tuple[ActionLogEntry, ...]


@dataclass(frozen=True)
class ActionResult:
    """action() / start_game() の戻り値"""
    state: GameState
    events: tuple[GameEvent, ...]
    waiting_for: WaitingFor | None  # None → ゲーム終了
