"""Модуль содержит структуры входящих запросов от пользователей."""
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, model_validator
from enums import CombinationType, CardSuit

class ActionType(str, Enum):
    """Доступные действия для игрока в его ход."""
    RAISE = "RAISE"          # Повысить / Поставить ставку
    CHALLENGE = "CHALLENGE"  # Сказать "Не верю" (Блеф)

class PlayerActionRequest(BaseModel):
    """Единая структура запроса для любого хода игрока."""
    player_id: str = Field(..., description="ID игрока, который делает ход")
    action: ActionType = Field(..., description="Тип действия")

    # Эти параметры обязательны, ТОЛЬКО если action == ActionType.RAISE
    type: Optional[CombinationType] = Field(None, description="Тип комбинации")
    rank_primary: Optional[int] = Field(None, ge=2, le=14, description="Старшая карта")
    rank_secondary: Optional[int] = Field(None, ge=2, le=14, description="Вторая карта")
    suit: Optional[CardSuit] = Field(None, description="Масть карты")

    @model_validator(mode="after")
    def validate_raise_fields(self) -> "PlayerActionRequest":
        """Проверяет корректность заполнения полей в зависимости от комбинации."""
        if self.action == ActionType.CHALLENGE:
            return self

        if not self.type:
            raise ValueError("Для действия RAISE необходимо указать тип комбинации (type)")

        # 1. Комбинации, требующие только rank_primary и БЕЗ масти
        if self.type in [
            CombinationType.HIGH_CARD, CombinationType.PAIR,
            CombinationType.SET, CombinationType.STREET,
            CombinationType.FLASH, CombinationType.KARE
        ]:
            if self.rank_primary is None:
                raise ValueError(f"Для комбинации {self.type} нужно rank_primary")
            if self.rank_secondary is not None or self.suit is not None:
                raise ValueError(f"Для {self.type} поля secondary и suit должны быть None")

        # 2. Комбинации, требующие ДВА достоинства и БЕЗ масти
        elif self.type in [CombinationType.TWO_PAIRS, CombinationType.FULL_HOUSE]:
            if self.rank_primary is None or self.rank_secondary is None:
                raise ValueError(f"Для {self.type} требуются primary и secondary")
            if self.suit is not None:
                raise ValueError(f"Для комбинации {self.type} поле suit должно быть None")
            if self.rank_primary == self.rank_secondary:
                raise ValueError("Достоинства карт не могут совпадать")

        # 3. Стрит-Флеш требует достоинство (границу) и может иметь опциональную масть
        elif self.type == CombinationType.STREET_FLASH:
            if self.rank_primary is None:
                raise ValueError("Для Стрит-Флеша необходимо указать rank_primary")
            if self.rank_secondary is not None:
                raise ValueError("Для Стрит-Флеша поле rank_secondary должно быть None")

        # 4. Флеш-Рояль вообще НЕ требует достоинств, для него имеет значение только масть
        elif self.type == CombinationType.FLASH_ROYAL:
            if self.rank_primary is not None or self.rank_secondary is not None:
                raise ValueError("Для Флеш-Рояля поля rank_primary/rank_secondary не нужны")

        return self