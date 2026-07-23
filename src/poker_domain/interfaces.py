from abc import ABC, abstractmethod

from poker_domain.game_state import ActionResult, GameEvent, GameState, TableStatus
from poker_domain.value_objects.action import Action
from poker_domain.value_objects.chips import Chips


class PokerTableInterface(ABC):
    """`PokerTable` の公開インターフェース。

    service レイヤーからの呼び出し窓口はこれだけ。
    """

    @abstractmethod
    def add_player(self, player_id: str, chips: Chips) -> GameEvent:
        """プレイヤーを追加する。

        Args:
            player_id: プレイヤーを一意に識別するID。
            chips: 持ち込みチップ額。

        Returns:
            `EventType.PLAYER_JOINED` の `GameEvent`。
        """
        ...

    @abstractmethod
    def remove_player(self, player_id: str) -> GameEvent:
        """プレイヤーを削除する。

        Args:
            player_id: 離席させるプレイヤーのID。

        Returns:
            `EventType.PLAYER_LEFT` の `GameEvent`。
        """
        ...

    @abstractmethod
    def start_game(self) -> ActionResult:
        """ゲームを開始する (ブラインド徴収・カード配布)。

        Returns:
            開始直後の状態を含む `ActionResult`。
        """
        ...

    @abstractmethod
    def action(self, player_id: str, action: Action) -> ActionResult:
        """プレイヤーのアクションを入力し、結果を返す。

        Args:
            player_id: アクションを取るプレイヤーのID。
            action: `Fold` / `Check` / `Call` / `Bet` / `Raise` のいずれか。

        Returns:
            適用後の状態を含む `ActionResult`。
        """
        ...

    @abstractmethod
    def get_state(self, viewer_player_id: str | None = None) -> GameState:
        """現在のゲーム状態のスナップショットを返す。

        Args:
            viewer_player_id: 指定すると、そのプレイヤーのホールカードのみ公開される。

        Returns:
            現在の `GameState` スナップショット。
        """
        ...

    @abstractmethod
    def level_up(self) -> GameEvent:
        """ブラインド/アンティのレベルを1段階上昇させる (最終レベルの場合は据え置き)。

        Returns:
            `EventType.LEVEL_UP` の `GameEvent`。
        """
        ...

    @abstractmethod
    def get_table_status(self) -> TableStatus:
        """テーブルのライフサイクル状態 (参加募集中/プレイ中/クローズ/その他) を返す。

        Returns:
            `TableStatus`。
        """
        ...
