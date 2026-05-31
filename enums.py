"""Модуль содержит перечисления для типов покерных комбинаций и мастей."""
from enum import Enum, IntEnum

class CombinationType(IntEnum):
    """Иерархия комбинаций по возрастанию силы (от 1 до 10)."""
    HIGH_CARD = 1
    PAIR = 2
    TWO_PAIRS = 3
    SET = 4
    STREET = 5
    FULL_HOUSE = 6
    FLASH = 7
    KARE = 8
    STREET_FLASH = 9
    FLASH_ROYAL = 10

class CardSuit(str, Enum):
    """Масти карт для Стрит-Флеша и Рояля."""
    CLUBS = "C"    # ♣
    DIAMONDS = "D" # ♦
    HEARTS = "H"   # ♥
    SPADES = "S"   # ♠

class GameStatus(str, Enum):
    """Статусы игры для управления экраном фронтенда."""
    LOBBY = "LOBBY"          # Игроки собираются
    PLAYING = "PLAYING"      # Идёт активный раунд (игроки делают ставки)
    SHOWDOWN = "SHOWDOWN"    # Кто-то крикнул "Не верю!", показываем все карты
    GAME_OVER = "GAME_OVER"  # Один игрок набрал 6 карт и выбыл (игра завершена)
