from dataclasses import dataclass, field

from poker_domain.value_objects.card import Card
from poker_domain.value_objects.chips import Chips


@dataclass
class Player:
    """テーブルプレイヤー。エンティティなので変動状態を持つ。"""

    player_id: str
    chips: Chips
    hole_cards: tuple[Card, ...] = ()
    current_bet: Chips = field(default_factory=lambda: Chips(0))
    folded: bool = False
    is_all_in: bool = False

    def reset_for_new_hand(self) -> None:
        """次のハンド開始時のリセット"""
        self.hole_cards = ()
        self.current_bet = Chips(0)
        self.folded = False
        self.is_all_in = False

    @property
    def is_active(self) -> bool:
        """フォールドもアールインもしていない"""
        return not self.folded and not self.is_all_in

    @property
    def is_in_hand(self) -> bool:
        """フォールドしていない (all-in も含む)"""
        return not self.folded
