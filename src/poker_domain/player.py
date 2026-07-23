from dataclasses import dataclass, field

from poker_domain.value_objects.chips import Chips
from poker_domain.value_objects.hole_cards import HoleCards


@dataclass
class Player:
    """テーブルプレイヤー。エンティティなので変動状態を持つ。"""

    player_id: str
    chips: Chips
    hole_cards: HoleCards = field(default_factory=HoleCards)
    current_bet: Chips = field(default_factory=lambda: Chips(0))
    folded: bool = False
    is_all_in: bool = False
    total_contributed: Chips = field(default_factory=lambda: Chips(0))

    def reset_for_new_hand(self) -> None:
        """次のハンド開始時のリセット"""
        self.hole_cards = HoleCards()
        self.current_bet = Chips(0)
        self.folded = False
        self.is_all_in = False
        self.total_contributed = Chips(0)

    def _contribute(self, amount: int, *, affects_current_bet: bool = True) -> int:
        """
        チップを拠出する (ブラインド/アンティ/コール/ベット/レイズの共通処理)。
        保有チップ不足の場合は保有額全額に切り詰め、拠出後に0になれば is_all_in にする。
        実際に拠出された額を返す (呼び出し側でポット加算に使う)。

        `current_bet` はそのストリートで「対抗するために積んだ額」を表すため、
        ブラインド/コール/ベット/レイズでは加算するが、アンティは対抗額ではない
        ので `affects_current_bet=False` で呼び出し current_bet を変化させない。
        """
        paid = min(amount, self.chips.amount)
        self.chips = Chips(self.chips.amount - paid)
        if affects_current_bet:
            self.current_bet = self.current_bet + Chips(paid)
        self.total_contributed = self.total_contributed + Chips(paid)
        if self.chips.amount == 0:
            self.is_all_in = True
        return paid

    @property
    def is_active(self) -> bool:
        """フォールドもアールインもしていない"""
        return not self.folded and not self.is_all_in

    @property
    def is_in_hand(self) -> bool:
        """フォールドしていない (all-in も含む)"""
        return not self.folded
