"""Модуль содержит Pydantic схемы для игроков, карт и ставок."""
import time
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
            CombinationType.KARE
        ]:
            if self.rank_primary is None or self.rank_secondary is not None or self.suit is not None:
                raise ValueError("Некорректные параметры для базовой комбинации")
        if self.type in (CombinationType.FLASH, CombinationType.STREET_FLASH):
            if self.rank_primary is None or self.rank_secondary is not None:
                raise ValueError("Некорректные параметры для флеша / стрит-флеша")
        if self.type == CombinationType.FLASH_ROYAL:
            if self.rank_primary is not None or self.rank_secondary is not None:
                raise ValueError("Для Флеш-Рояля поля rank_primary/rank_secondary не нужны")
        return self

    def __gt__(self, other: Optional["Bid"]) -> bool:
        """Сравнивает текущую ставку с предыдущей (см. bid_comparison)."""
        from bid_comparison import is_bid_stronger

        return is_bid_stronger(self, other)

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
    deck: List[Card] = Field(
        default_factory=list, description="Неразданные карты (остаток колоды)"
    )
    elimination_limit: int = Field(
        6, ge=4, le=12, description="Сколько карт на руках — выбывание"
    )
    showdown_loser_id: Optional[str] = Field(
        None, description="ID проигравшего раунд (фаза вскрытия)"
    )
    showdown_message: Optional[str] = Field(
        None, description="Сообщение для экрана вскрытия"
    )
    showdown_combination_found: Optional[bool] = Field(
        None, description="Была ли комбинация на столе при вскрытии"
    )
    turn_deadline: Optional[float] = Field(
        None, description="Unix-время окончания хода (серверный таймер)"
    )
    turn_generation: int = Field(
        0, description="Счётчик смены хода (инвалидация устаревших таймеров)"
    )
    showdown_deadline: Optional[float] = Field(
        None, description="Unix-время автозавершения вскрытия"
    )
    last_activity_at: float = Field(
        default_factory=time.time,
        description="Unix-время последней активности в комнате (вход, ход, старт)",
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