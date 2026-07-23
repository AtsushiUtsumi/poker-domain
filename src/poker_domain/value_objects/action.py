from dataclasses import dataclass


@dataclass(frozen=True)
class Fold:
    pass


@dataclass(frozen=True)
class Check:
    pass


@dataclass(frozen=True)
class Call:
    pass


@dataclass(frozen=True)
class Bet:
    amount: int


@dataclass(frozen=True)
class Raise:
    amount: int


Action = Fold | Check | Call | Bet | Raise
