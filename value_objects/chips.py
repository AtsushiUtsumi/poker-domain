from dataclasses import dataclass


@dataclass(frozen=True)
class Chips:
    amount: int

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("チップは負にはなれません")

    def __add__(self, other: "Chips") -> "Chips":
        return Chips(self.amount + other.amount)

    def __sub__(self, other: "Chips") -> "Chips":
        return Chips(self.amount - other.amount)  # __post_init__ で負チェック

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Chips):
            return NotImplemented
        return self.amount == other.amount

    def __lt__(self, other: "Chips") -> bool:
        return self.amount < other.amount

    def __le__(self, other: "Chips") -> bool:
        return self.amount <= other.amount

    def __gt__(self, other: "Chips") -> bool:
        return self.amount > other.amount

    def __ge__(self, other: "Chips") -> bool:
        return self.amount >= other.amount

    def __hash__(self) -> int:
        return hash(self.amount)

    def __repr__(self) -> str:
        return f"Chips({self.amount})"
