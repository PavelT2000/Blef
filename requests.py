"""Модуль содержит структуры входящих запросов от пользователей."""

from enum import Enum

from typing import Optional

from pydantic import BaseModel, Field, model_validator

from enums import CombinationType, CardSuit





class JoinRequest(BaseModel):

    """Запрос на вход в лобби по имени."""

    name: str = Field(..., min_length=1, max_length=32)

    room_code: str = Field(..., min_length=4, max_length=8, description="Код комнаты")





class CreateRoomRequest(BaseModel):

    """Пустой запрос на создание комнаты (тело не обязательно)."""

    pass





class LeaveRequest(BaseModel):

    """Выход игрока из комнаты."""

    player_id: str = Field(..., description="ID игрока")

    room_code: str = Field(..., description="Код комнаты")





class StartGameRequest(BaseModel):

    """Запрос на ручной старт игры из лобби."""

    player_id: str = Field(..., description="ID игрока, инициирующего старт")

    room_code: str = Field(..., description="Код комнаты")






class FinishShowdownRequest(BaseModel):

    """Досрочное завершение паузы вскрытия."""

    player_id: str = Field(..., description="ID игрока")

    room_code: str = Field(..., description="Код комнаты")





class ResetRoomRequest(BaseModel):

    """Сброс комнаты в лобби (те же игроки)."""

    player_id: str = Field(..., description="ID игрока")

    room_code: str = Field(..., description="Код комнаты")





class ActionType(str, Enum):

    """Доступные действия для игрока в его ход."""

    RAISE = "RAISE"

    CHALLENGE = "CHALLENGE"





class PlayerActionRequest(BaseModel):

    """Единая структура запроса для любого хода игрока."""

    player_id: str = Field(..., description="ID игрока, который делает ход")

    room_code: str = Field(..., description="Код комнаты")

    action: ActionType = Field(..., description="Тип действия")



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



        if self.type in [

            CombinationType.HIGH_CARD, CombinationType.PAIR,

            CombinationType.SET, CombinationType.STREET,

            CombinationType.KARE

        ]:

            if self.rank_primary is None:

                raise ValueError(f"Для комбинации {self.type} нужно rank_primary")

            if self.rank_secondary is not None or self.suit is not None:

                raise ValueError(f"Для {self.type} поля secondary и suit должны быть None")



        elif self.type == CombinationType.FLASH:

            if self.rank_primary is None:

                raise ValueError("Для Флеша необходимо указать rank_primary")

            if self.rank_secondary is not None:

                raise ValueError("Для Флеша поле rank_secondary должно быть None")



        elif self.type in [CombinationType.TWO_PAIRS, CombinationType.FULL_HOUSE]:

            if self.rank_primary is None or self.rank_secondary is None:

                raise ValueError(f"Для {self.type} требуются primary и secondary")

            if self.suit is not None:

                raise ValueError(f"Для комбинации {self.type} поле suit должно быть None")

            if self.rank_primary == self.rank_secondary:

                raise ValueError("Достоинства карт не могут совпадать")



        elif self.type == CombinationType.STREET_FLASH:

            if self.rank_primary is None:

                raise ValueError("Для Стрит-Флеша необходимо указать rank_primary")

            if self.rank_secondary is not None:

                raise ValueError("Для Стрит-Флеша поле rank_secondary должно быть None")



        elif self.type == CombinationType.FLASH_ROYAL:

            if self.rank_primary is not None or self.rank_secondary is not None:

                raise ValueError("Для Флеш-Рояля поля rank_primary/rank_secondary не нужны")



        return self

