class PokerError(Exception):
    """poker_domain 全体の基底例外"""
    pass


class InvalidActionError(PokerError):
    """無効なアクション"""
    pass


class InsufficientChipsError(InvalidActionError):
    """チップ不足"""
    pass


class InvalidPlayerError(PokerError):
    """無効なプレイヤー操作"""
    pass


class TableFullError(PokerError):
    """テーブル満席"""
    pass


class NotEnoughPlayersError(PokerError):
    """プレイヤー数不足"""
    pass


class GameAlreadyStartedError(PokerError):
    """ゲーム開始後に許可されない操作"""
    pass


class DeckEmptyError(PokerError):
    """デッキのカード不足"""
    pass
