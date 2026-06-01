"""Сравнение силы ставок по правилам bets.txt."""
from typing import Optional, Protocol

from enums import CombinationType


class BidLike(Protocol):
    type: CombinationType
    rank_primary: Optional[int]
    rank_secondary: Optional[int]
    suit: Optional[object]


def _rank(value: Optional[int]) -> int:
    return value or 0


def _two_pairs_key(primary: Optional[int], secondary: Optional[int]) -> tuple[int, int]:
    """Старшая пара, затем младшая (порядок полей в форме не важен)."""
    if primary is None or secondary is None:
        return (0, 0)
    high, low = max(primary, secondary), min(primary, secondary)
    return (high, low)


def _full_house_key(primary: Optional[int], secondary: Optional[int]) -> tuple[int, int]:
    """Сначала тройка (rank_primary), затем пара (rank_secondary)."""
    return (_rank(primary), _rank(secondary))


def _same_type_params_stronger(new: BidLike, last: BidLike) -> bool:
    """True, если при одинаковом типе new строго сильнее last."""
    if new.type in (CombinationType.FLASH, CombinationType.STREET_FLASH, CombinationType.FLASH_ROYAL):
        if new.suit and not last.suit:
            return True
        if not new.suit and last.suit:
            return False

    if new.type in (CombinationType.FLASH, CombinationType.STREET_FLASH):
        if _rank(new.rank_primary) != _rank(last.rank_primary):
            return _rank(new.rank_primary) > _rank(last.rank_primary)
        return False

    if new.type == CombinationType.FLASH_ROYAL:
        return False

    if new.type == CombinationType.TWO_PAIRS:
        return _two_pairs_key(new.rank_primary, new.rank_secondary) > _two_pairs_key(
            last.rank_primary, last.rank_secondary
        )

    if new.type == CombinationType.FULL_HOUSE:
        return _full_house_key(new.rank_primary, new.rank_secondary) > _full_house_key(
            last.rank_primary, last.rank_secondary
        )

    return _rank(new.rank_primary) > _rank(last.rank_primary)


def is_bid_stronger(new_bid: BidLike, last_bid: Optional[BidLike]) -> bool:
    """Возвращает True, если new_bid строго сильнее last_bid."""
    if last_bid is None:
        return True

    if new_bid.type != last_bid.type:
        return new_bid.type > last_bid.type

    return _same_type_params_stronger(new_bid, last_bid)
