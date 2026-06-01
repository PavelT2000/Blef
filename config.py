"""Константы приложения."""
from deck import DECK_SIZE

TURN_TIMEOUT_SECONDS = 15
SHOWDOWN_TIMEOUT_SECONDS = 10
MIN_PLAYERS = 2
MAX_PLAYERS = 13
ROOM_CODE_LENGTH = 6
MIN_ELIMINATION_CARDS = 4
MAX_ELIMINATION_CARDS = 12


def compute_elimination_limit(num_players: int) -> int:
    """Лимит карт для выбывания: clamp(trunc(52 / n), 4, 12)."""
    if num_players < 1:
        return MAX_ELIMINATION_CARDS
    raw = DECK_SIZE // num_players
    return max(MIN_ELIMINATION_CARDS, min(MAX_ELIMINATION_CARDS, raw))
