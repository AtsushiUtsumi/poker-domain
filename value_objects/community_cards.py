from poker_domain.value_objects.card import Card


class CommunityCards(tuple[Card, ...]):
    """ボード(コミュニティカード)。tuple[Card, ...] のサブクラスで、挙動は tuple と完全互換"""

    __slots__ = ()
