from dataclasses import dataclass
from enum import Enum
from typing import Any

from poker_domain.value_objects.card import Card
from poker_domain.value_objects.chips import Chips
from poker_domain.value_objects.action import Action


class GamePhase(Enum):
    WAITING = "waiting"       # プレイヤー待機中
    PRE_FLOP = "pre_flop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"


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


@dataclass(frozen=True)
class GameEvent:
    event_type: EventType
    payload: dict[str, Any]


@dataclass(frozen=True)
class WaitingFor:
    """poker_domain が次に誰のアクションを待っているか"""
    player_id: str
    valid_actions: tuple[type, ...]  # e.g. (Fold, Check, Raise)
    timeout_seconds: int


@dataclass(frozen=True)
class PlayerState:
    """スナップショット用のプレイヤー状態 (不変)"""
    player_id: str
    chips: Chips
    current_bet: Chips
    folded: bool
    is_all_in: bool
    hole_cards: tuple[Card, ...] | None  # viewer のカードだけ見える


@dataclass(frozen=True)
class GameState:
    """テーブル全体のスナップショット (不変)"""
    table_id: str
    phase: GamePhase
    pot: Chips
    current_bet: Chips
    community_cards: tuple[Card, ...]
    players: tuple[PlayerState, ...]
    current_player_id: str | None
    dealer_id: str
    small_blind: Chips
    big_blind: Chips


@dataclass(frozen=True)
class ActionResult:
    """action() / start_game() の戻り値"""
    state: GameState
    events: tuple[GameEvent, ...]
    waiting_for: WaitingFor | None  # None → ゲーム終了
