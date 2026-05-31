"""Модуль содержит Pydantic схемы для игроков, карт и ставок."""
from typing import Optional, List
from pydantic import BaseModel, Field, model_validator
from enums import CombinationType, CardSuit, GameStatus

class Card(BaseModel):
    """Модель карты."""
    rank: int = Field(..., ge=2, le=14, description="2-10, 11=V, 12=D, 13=K, 14=T")
    suit: CardSuit = Field(..., description="Масть")

class Bid(BaseModel):
    """Схема ставки игрока в текущем раунде."""
    player_id: str = Field(..., description="Кто делает ставку")
    type: CombinationType = Field(..., description="Какую комбинацию заявляет")
    rank_primary: Optional[int] = Field(
        None, ge=2, le=14, description="Основная карта (11=V, 12=D, 13=K, 14=T)"
    )
    rank_secondary: Optional[int] = Field(
        None, ge=2, le=14, description="Вторая карта (для 2 пар и фулла)"
    )
    suit: Optional[CardSuit] = Field(None, description="Масть (если выбрана)")

    @model_validator(mode="after")
    def validate_bid_structure(self) -> "Bid":
        """Гарантирует, что в сохраненной ставке нет лишних полей."""
        if self.type in [
            CombinationType.HIGH_CARD, CombinationType.PAIR,
            CombinationType.SET, CombinationType.STREET,
            CombinationType.FLASH, CombinationType.KARE
        ]:
            if self.rank_primary is None or self.rank_secondary is not None or self.suit is not None:
                raise ValueError("Некорректные параметры для базовой комбинации")
        return self

    def __gt__(self, other: Optional["Bid"]) -> bool:
        """Сравнивает текущую ставку с предыдущей.

        Возвращает True, если текущая ставка строго сильнее.
        """
        if other is None:
            return True

        # 1. По типу комбинации (Иерархия от 1 до 10)
        if self.type != other.type:
            return self.type > other.type

        # Если тип одинаковый, сравниваем параметры по правилам bets.txt
        # У Стрит-Флеша и Рояля опциональная масть усиливает ставку
        if self.type in [CombinationType.STREET_FLASH, CombinationType.FLASH_ROYAL]:
            if self.suit and not other.suit:
                return True
            if not self.suit and other.suit:
                return False

        # Сравниваем по первичному рангу
        sp = self.rank_primary or 0
        op = other.rank_primary or 0
        if sp != op:
            return sp > op

        # Сравниваем по вторичному рангу (Две пары, Фулл хаус)
        ss = self.rank_secondary or 0
        os = other.rank_secondary or 0
        if ss != os:
            return ss > os

        return False

class Player(BaseModel):
    """Схема состояния конкретного игрока."""
    id: str = Field(..., description="Уникальный ID (токен) игрока")
    name: str = Field(..., description="Отображаемое имя")
    cards: List[Card] = Field(
        default_factory=list, description="Карты на руках"
    )
    last_bid: Optional[Bid] = Field(
        None, description="Последняя ставка игрока"
    )
    is_eliminated: bool = Field(
        False, description="Выбыл ли игрок из игры"
    )

    @property
    def cards_count(self) -> int:
        """Хелпер для получения количества карт."""
        return len(self.cards)

class GameState(BaseModel):
    """Структура текущего состояния игровой комнаты."""
    room_id: str = Field(..., description="Уникальный ID комнаты")
    status: GameStatus = Field(
        GameStatus.LOBBY, description="Текущая стадия игры"
    )
    players: List[Player] = Field(
        default_factory=list, description="Список участников"
    )
    current_player_idx: int = Field(
        0, description="Индекс игрока в списке players, чей сейчас ход"
    )
    bid_history: List[Bid] = Field(
        default_factory=list, description="История ставок в текущем раунде"
    )
    logs: List[str] = Field(
        default_factory=list, description="История игровых логов (кто кого вскрыл, кто выбыл)"
    )

    @property
    def current_player(self) -> Optional[Player]:
        """Хелпер для быстрого получения ходящего игрока."""
        if not self.players:
            return None
        return self.players[self.current_player_idx]

    @property
    def last_bid(self) -> Optional[Bid]:
        """Возвращает самую последнюю ставку за столом."""
        if not self.bid_history:
            return None
        return self.bid_history[-1]