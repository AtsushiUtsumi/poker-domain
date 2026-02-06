from dataclasses import dataclass
from typing import Union


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


Action = Union[Fold, Check, Call, Bet, Raise]
