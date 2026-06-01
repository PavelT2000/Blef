"""Проверка комбинаций на столе и логирование в файл."""
import logging
from collections import Counter
from pathlib import Path

from enums import CombinationType, CardSuit
from schemas import Bid, Card, Player

LOG_FILE = Path(__file__).parent / "combination_checks.log"

_logger = logging.getLogger("blef.combination")
if not _logger.handlers:
    _logger.setLevel(logging.INFO)
    _handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    _handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    _logger.addHandler(_handler)

RANK_LABELS = {11: "V", 12: "D", 13: "K", 14: "T"}


def _format_card(card: Card) -> str:
    rank = RANK_LABELS.get(card.rank, str(card.rank))
    suit = card.suit.value if isinstance(card.suit, CardSuit) else str(card.suit)
    return f"{rank}{suit}"


def _collect_all_table_cards(players: list[Player]) -> list[Card]:
    """Все карты всех игроков за столом (включая выбывших)."""
    cards: list[Card] = []
    for player in players:
        cards.extend(player.cards)
    return cards


def _street_satisfied(rank_counts: Counter, p_rank: int | None) -> bool:
    """Стрит: 5 подряд; младшая карта стрита >= нижней границы ставки (включительно)."""
    if p_rank is None:
        return False

    for start in range(max(2, p_rank), 11):
        if start + 4 <= 14:
            if all(rank_counts.get(r, 0) >= 1 for r in range(start, start + 5)):
                return True

    if p_rank <= 2 and all(rank_counts.get(r, 0) >= 1 for r in (2, 3, 4, 5, 14)):
        return True

    return False


def _street_flash_satisfied(
    all_cards: list[Card], rank_counts: Counter, p_rank: int | None, suit
) -> bool:
    if p_rank is None:
        return False

    if suit is not None:
        for start in range(max(2, p_rank), 11):
            if start + 4 <= 14:
                if all(
                    any(c.rank == r and c.suit == suit for c in all_cards)
                    for r in range(start, start + 5)
                ):
                    return True
        if p_rank <= 2 and all(
            any(c.rank == r and c.suit == suit for c in all_cards)
            for r in (2, 3, 4, 5, 14)
        ):
            return True
        return False

    return _street_satisfied(rank_counts, p_rank)


def _log_combination_check(
    players: list[Player],
    bid: Bid,
    all_cards: list[Card],
    rank_counts: Counter,
    result: bool,
) -> None:
    lines = [
        "=" * 60,
        f"Проверка: {bid.type.name} | primary={bid.rank_primary} secondary={bid.rank_secondary} suit={bid.suit}",
        f"Результат: {'НАЙДЕНА' if result else 'НЕ НАЙДЕНА'}",
        f"Карт на столе всего: {len(all_cards)}",
        "Карты по игрокам:",
    ]
    for player in players:
        cards_str = ", ".join(_format_card(c) for c in player.cards) or "—"
        status = " (выбыл)" if player.is_eliminated else ""
        lines.append(f"  {player.name}{status}: [{cards_str}]")

    pool_str = ", ".join(_format_card(c) for c in all_cards) or "—"
    lines.append(f"Общий пул: [{pool_str}]")

    rank_summary = ", ".join(
        f"{RANK_LABELS.get(r, r)}×{cnt}" for r, cnt in sorted(rank_counts.items())
    )
    lines.append(f"Ранги в пуле: {rank_summary or '—'}")

    if bid.type == CombinationType.STREET and bid.rank_primary is not None:
        lines.append(f"Нижняя граница стрита в ставке: {bid.rank_primary}")

    _logger.info("\n".join(lines))


def check_combination_on_table(players: list[Player], bid: Bid) -> bool:
    """Проверяет, собрана ли заявленная комбинация из всех карт на столе."""
    all_cards = _collect_all_table_cards(players)
    rank_counts = Counter(c.rank for c in all_cards)
    p_rank = bid.rank_primary
    s_rank = bid.rank_secondary

    result = False

    if bid.type == CombinationType.HIGH_CARD:
        result = rank_counts.get(p_rank, 0) >= 1

    elif bid.type == CombinationType.PAIR:
        result = rank_counts.get(p_rank, 0) >= 2

    elif bid.type == CombinationType.TWO_PAIRS:
        result = rank_counts.get(p_rank, 0) >= 2 and rank_counts.get(s_rank, 0) >= 2

    elif bid.type == CombinationType.SET:
        result = rank_counts.get(p_rank, 0) >= 3

    elif bid.type == CombinationType.KARE:
        result = rank_counts.get(p_rank, 0) >= 4

    elif bid.type == CombinationType.FULL_HOUSE:
        result = rank_counts.get(p_rank, 0) >= 3 and rank_counts.get(s_rank, 0) >= 2

    elif bid.type == CombinationType.STREET:
        result = _street_satisfied(rank_counts, p_rank)

    elif bid.type == CombinationType.FLASH:
        if bid.suit is not None:
            suited = [c for c in all_cards if c.suit == bid.suit and c.rank >= p_rank]
            result = len(suited) >= 5
        else:
            result = sum(1 for c in all_cards if c.rank >= p_rank) >= 5

    elif bid.type == CombinationType.STREET_FLASH:
        result = _street_flash_satisfied(all_cards, rank_counts, p_rank, bid.suit)

    elif bid.type == CombinationType.FLASH_ROYAL:
        royal_ranks = (10, 11, 12, 13, 14)
        if bid.suit is not None:
            result = all(
                any(c.rank == r and c.suit == bid.suit for c in all_cards)
                for r in royal_ranks
            )
        else:
            result = all(rank_counts.get(r, 0) >= 1 for r in royal_ranks)

    _log_combination_check(players, bid, all_cards, rank_counts, result)
    return result
