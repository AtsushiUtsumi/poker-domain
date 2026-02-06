from abc import ABC, abstractmethod

from poker_domain.value_objects.action import Action
from poker_domain.value_objects.chips import Chips
from poker_domain.game_state import ActionResult, GameState, GameEvent


class PokerTableInterface(ABC):
    """
    PokerTable の公開インターフェース。
    service レイヤーからの呼び出し窓口はこれだけ。
    """

    @abstractmethod
    def add_player(self, player_id: str, chips: Chips) -> GameEvent:
        """プレイヤーを追加する"""
        ...

    @abstractmethod
    def remove_player(self, player_id: str) -> GameEvent:
        """プレイヤーを削除する"""
        ...

    @abstractmethod
    def start_game(self) -> ActionResult:
        """ゲームを開始する (ブラインド徴収・カード配布)"""
        ...

    @abstractmethod
    def action(self, player_id: str, action: Action) -> ActionResult:
        """プレイヤーのアクションを入力し、結果を返す"""
        ...

    @abstractmethod
    def get_state(self, viewer_player_id: str | None = None) -> GameState:
        """現在のゲーム状態のスナップショットを返す"""
        ...
