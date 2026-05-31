"""Модуль управления SSE-подключениями игроков."""
import asyncio
from typing import Dict, Set

class SSEManager:
    """Менеджер для отправки уведомлений игрокам в реальном времени."""
    def __init__(self):
        # Храним очереди сообщений для каждого игрока: {player_id: set_of_queues}
        self._connections: Dict[str, Set[asyncio.Queue]] = {}

    async def subscribe(self, player_id: str) -> asyncio.Queue:
        """Регистрирует поток для игрока и возвращает его личную очередь."""
        queue = asyncio.Queue()
        if player_id not in self._connections:
            self._connections[player_id] = set()
        self._connections[player_id].add(queue)
        return queue

    def unsubscribe(self, player_id: str, queue: asyncio.Queue) -> None:
        """Удаляет закрытое соединение из списка."""
        if player_id in self._connections:
            self._connections[player_id].discard(queue)
            if not self._connections[player_id]:
                del self._connections[player_id]

    async def broadcast_to_player(self, player_id: str, data: str) -> None:
        """Отправляет JSON-строку во все открытые вкладки конкретного игрока."""
        if player_id in self._connections:
            for queue in self._connections[player_id]:
                await queue.put(data)

# Создаем глобальный синглтон менеджера
sse_manager = SSEManager()