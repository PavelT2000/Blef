"""Управление игровыми комнатами, таймерами хода и очисткой пустых комнат."""
import asyncio
import json
import secrets
import string
import time
import uuid
from typing import Optional

from enums import CombinationType, GameStatus
from game_logic import finalize_showdown, get_masked_game_state, handle_player_action
from requests import ActionType, PlayerActionRequest
from schemas import GameState, Player
from config import (
    MAX_PLAYERS,
    MIN_PLAYERS,
    ROOM_CODE_LENGTH,
    SHOWDOWN_TIMEOUT_SECONDS,
    TURN_TIMEOUT_SECONDS,
    compute_elimination_limit,
)
from deck import deal_initial_cards, DECK_SIZE
from sse_manager import sse_manager

ROOM_ALPHABET = string.ascii_uppercase + string.digits


def generate_player_id() -> str:
    return uuid.uuid4().hex


def find_player(state: GameState, player_id: str) -> Optional[Player]:
    return next((p for p in state.players if p.id == player_id), None)


def build_auto_turn_action(state: GameState) -> PlayerActionRequest:
    """При таймауте: «Не верю», если есть ставка; иначе минимальная заявка — старшая карта 2."""
    current = state.current_player
    if not current:
        raise RuntimeError("Нет активного игрока для автохода")

    code = state.room_id
    if state.last_bid:
        return PlayerActionRequest(
            player_id=current.id,
            room_code=code,
            action=ActionType.CHALLENGE,
        )
    return PlayerActionRequest(
        player_id=current.id,
        room_code=code,
        action=ActionType.RAISE,
        type=CombinationType.HIGH_CARD,
        rank_primary=2,
    )


class RoomManager:
  def __init__(self) -> None:
    self._rooms: dict[str, GameState] = {}
    self._player_room: dict[str, str] = {}
    self._turn_tasks: dict[str, asyncio.Task] = {}
    self._showdown_tasks: dict[str, asyncio.Task] = {}
    self._lock = asyncio.Lock()

  def _generate_room_code(self) -> str:
    while True:
      code = "".join(secrets.choice(ROOM_ALPHABET) for _ in range(ROOM_CODE_LENGTH))
      if code not in self._rooms:
        return code

  def get_room(self, room_code: str) -> Optional[GameState]:
    return self._rooms.get(room_code.upper())

  def get_room_for_player(self, player_id: str) -> Optional[GameState]:
    code = self._player_room.get(player_id)
    if not code:
      return None
    return self._rooms.get(code)

  def room_code_for_player(self, player_id: str) -> Optional[str]:
    return self._player_room.get(player_id)

  async def create_room(self) -> tuple[str, GameState]:
    async with self._lock:
      code = self._generate_room_code()
      state = GameState(
        room_id=code,
        status=GameStatus.LOBBY,
        players=[],
        logs=[f"Комната {code} создана. Поделитесь кодом или ссылкой для входа."],
      )
      self._rooms[code] = state
      return code, state

  def _cancel_turn_timer(self, room_code: str) -> None:
    task = self._turn_tasks.pop(room_code, None)
    if task and not task.done():
      task.cancel()

  def _cancel_showdown_timer(self, room_code: str) -> None:
    task = self._showdown_tasks.pop(room_code, None)
    if task and not task.done():
      task.cancel()

  def _cancel_all_timers(self, room_code: str) -> None:
    self._cancel_turn_timer(room_code)
    self._cancel_showdown_timer(room_code)

  def _schedule_turn_timer(self, room_code: str) -> None:
    state = self._rooms.get(room_code)
    if not state or state.status != GameStatus.PLAYING:
      return
    current = state.current_player
    if not current or current.is_eliminated:
      return

    self._cancel_turn_timer(room_code)
    state.turn_generation += 1
    state.turn_deadline = time.time() + TURN_TIMEOUT_SECONDS
    generation = state.turn_generation
    self._turn_tasks[room_code] = asyncio.create_task(
      self._turn_timer_worker(room_code, generation)
    )

  def _schedule_showdown_timer(self, room_code: str) -> None:
    state = self._rooms.get(room_code)
    if not state or state.status != GameStatus.SHOWDOWN:
      return

    self._cancel_showdown_timer(room_code)
    state.showdown_deadline = time.time() + SHOWDOWN_TIMEOUT_SECONDS
    self._showdown_tasks[room_code] = asyncio.create_task(
      self._showdown_timer_worker(room_code)
    )

  async def _turn_timer_worker(self, room_code: str, generation: int) -> None:
    try:
      await asyncio.sleep(TURN_TIMEOUT_SECONDS)
      async with self._lock:
        state = self._rooms.get(room_code)
        if not state or state.status != GameStatus.PLAYING:
          return
        if state.turn_generation != generation:
          return
        current = state.current_player
        if not current:
          return

        try:
          request = build_auto_turn_action(state)
          state = handle_player_action(state, request)
          self._rooms[room_code] = state
          action_label = (
            "«Не верю» (таймаут)"
            if request.action == ActionType.CHALLENGE
            else "Старшая карта 2 (таймаут)"
          )
          state.logs.append(f"{current.name}: автоход — {action_label}")
        except Exception as exc:
          state.logs.append(f"Ошибка автохода для {current.name}: {exc}")
          return

        await self._after_state_change_locked(room_code, state)
    except asyncio.CancelledError:
      pass

  async def _showdown_timer_worker(self, room_code: str) -> None:
    try:
      await asyncio.sleep(SHOWDOWN_TIMEOUT_SECONDS)
      async with self._lock:
        state = self._rooms.get(room_code)
        if not state or state.status != GameStatus.SHOWDOWN:
          return
        state = finalize_showdown(state)
        self._rooms[room_code] = state
        await self._after_state_change_locked(room_code, state)
    except asyncio.CancelledError:
      pass

  async def _after_state_change_locked(self, room_code: str, state: GameState) -> None:
    """Вызывается под lock после смены состояния."""
    active = [p for p in state.players if not p.is_eliminated]
    if state.status == GameStatus.PLAYING and len(active) < MIN_PLAYERS:
      state.status = GameStatus.GAME_OVER
      winner = active[0].name if active else "Никто"
      state.logs.append(f"ИГРА ОКОНЧЕНА! Недостаточно игроков. Победитель: {winner}")
      self._cancel_all_timers(room_code)
    elif state.status == GameStatus.SHOWDOWN:
      self._cancel_turn_timer(room_code)
      self._schedule_showdown_timer(room_code)
    elif state.status == GameStatus.PLAYING:
      self._cancel_showdown_timer(room_code)
      state.showdown_deadline = None
      self._schedule_turn_timer(room_code)
    elif state.status in (GameStatus.GAME_OVER, GameStatus.LOBBY):
      self._cancel_all_timers(room_code)
      state.turn_deadline = None
      state.showdown_deadline = None

    await self.broadcast_room(room_code)

  async def broadcast_room(self, room_code: str) -> None:
    state = self._rooms.get(room_code)
    if not state:
      return
    for player in state.players:
      safe_state = get_masked_game_state(state, player.id)
      payload = f"data: {json.dumps(safe_state, ensure_ascii=False)}\n\n"
      await sse_manager.broadcast_to_player(player.id, payload)

  async def _destroy_room_if_empty(self, room_code: str) -> bool:
    """Удаляет комнату без игроков. Возвращает True, если комната удалена."""
    state = self._rooms.get(room_code)
    if not state or state.players:
      return False

    self._cancel_all_timers(room_code)
    for pid in list(self._player_room):
      if self._player_room.get(pid) == room_code:
        del self._player_room[pid]
    del self._rooms[room_code]
    return True

  async def remove_player(self, room_code: str, player_id: str) -> Optional[GameState]:
    room_code = room_code.upper()
    async with self._lock:
      state = self._rooms.get(room_code)
      if not state:
        return None

      player = find_player(state, player_id)
      if not player:
        return state

      was_current = (
        state.status == GameStatus.PLAYING
        and state.current_player
        and state.current_player.id == player_id
      )

      state.players = [p for p in state.players if p.id != player_id]
      state.logs.append(f"{player.name} покинул комнату")
      self._player_room.pop(player_id, None)

      if not state.players:
        await self._destroy_room_if_empty(room_code)
        closed_payload = 'data: {"room_closed": true}\n\n'
        await sse_manager.broadcast_to_player(player_id, closed_payload)
        return None

      if state.status == GameStatus.PLAYING:
        active = [p for p in state.players if not p.is_eliminated]
        if len(active) < MIN_PLAYERS:
          state.status = GameStatus.GAME_OVER
          winner = active[0].name if active else "Никто"
          state.logs.append(f"ИГРА ОКОНЧЕНА! Победитель: {winner}")
          self._cancel_all_timers(room_code)
        elif was_current and state.status == GameStatus.PLAYING:
          if state.current_player_idx >= len(state.players):
            state.current_player_idx = 0
          from game_logic import next_player

          next_player(state)
          self._schedule_turn_timer(room_code)

      await self.broadcast_room(room_code)
      return state

  async def join_room(self, room_code: str, name: str) -> tuple[Player, GameState]:
    room_code = room_code.upper()
    async with self._lock:
      state = self._rooms.get(room_code)
      if not state:
        raise ValueError("Комната не найдена")
      if state.status != GameStatus.LOBBY:
        raise ValueError("Игра уже идёт. Дождитесь окончания или создайте новую комнату.")
      if any(p.name.lower() == name.lower() for p in state.players):
        raise ValueError("Игрок с таким именем уже в комнате")
      if len(state.players) >= MAX_PLAYERS:
        raise ValueError(f"В комнате уже максимум {MAX_PLAYERS} игроков")

      player = Player(
        id=generate_player_id(),
        name=name,
        cards=[],
        last_bid=None,
        is_eliminated=False,
      )
      state.players.append(player)
      self._player_room[player.id] = room_code
      state.logs.append(
        f"{name} присоединился ({len(state.players)}/{MAX_PLAYERS})"
      )
      await self.broadcast_room(room_code)
      return player, state

  async def start_game(self, room_code: str, player_id: str) -> GameState:
    room_code = room_code.upper()
    async with self._lock:
      state = self._rooms.get(room_code)
      if not state:
        raise ValueError("Комната не найдена")
      if find_player(state, player_id) is None:
        raise ValueError("Игрок не найден в этой комнате")
      if state.status != GameStatus.LOBBY:
        raise ValueError("Игра уже началась")
      if len(state.players) < MIN_PLAYERS:
        raise ValueError(f"Для старта нужно минимум {MIN_PLAYERS} игрока")
      elimination_limit = compute_elimination_limit(len(state.players))
      if len(state.players) * elimination_limit > DECK_SIZE:
        raise ValueError(
          f"При {len(state.players)} игроках и лимите {elimination_limit} "
          f"не хватит колоды ({DECK_SIZE} карт)."
        )

      state.elimination_limit = elimination_limit
      deal_initial_cards(state)
      state.status = GameStatus.PLAYING
      state.current_player_idx = 0
      state.bid_history = []
      state.logs.append(
        f"Игра началась! Колода: {DECK_SIZE} карт. "
        f"Выбывание при {elimination_limit} картах. Ход: {TURN_TIMEOUT_SECONDS} сек."
      )
      await self._after_state_change_locked(room_code, state)
      return state

  async def player_action(
    self, room_code: str, request: PlayerActionRequest
  ) -> GameState:
    room_code = room_code.upper()
    async with self._lock:
      state = self._rooms.get(room_code)
      if not state:
        raise ValueError("Комната не найдена")
      if find_player(state, request.player_id) is None:
        raise ValueError("Игрок не найден")
      if state.status != GameStatus.PLAYING:
        raise ValueError("Ходы доступны только во время активной игры")

      self._cancel_turn_timer(room_code)
      state = handle_player_action(state, request)
      self._rooms[room_code] = state
      await self._after_state_change_locked(room_code, state)
      return state

  async def finish_showdown(self, room_code: str, player_id: str) -> GameState:
    room_code = room_code.upper()
    async with self._lock:
      state = self._rooms.get(room_code)
      if not state:
        raise ValueError("Комната не найдена")
      if find_player(state, player_id) is None:
        raise ValueError("Игрок не найден")
      if state.status != GameStatus.SHOWDOWN:
        return state

      self._cancel_showdown_timer(room_code)
      state = finalize_showdown(state)
      self._rooms[room_code] = state
      await self._after_state_change_locked(room_code, state)
      return state

  async def reset_room(self, room_code: str, player_id: str) -> GameState:
    room_code = room_code.upper()
    async with self._lock:
      state = self._rooms.get(room_code)
      if not state:
        raise ValueError("Комната не найдена")
      if find_player(state, player_id) is None:
        raise ValueError("Игрок не найден")

      self._cancel_all_timers(room_code)
      code = state.room_id
      kept_players = [
        Player(
          id=p.id,
          name=p.name,
          cards=[],
          last_bid=None,
          is_eliminated=False,
        )
        for p in state.players
      ]
      new_state = GameState(
        room_id=code,
        status=GameStatus.LOBBY,
        players=kept_players,
        logs=[f"Комната {code} сброшена. Ожидание игроков."],
      )
      for p in kept_players:
        self._player_room[p.id] = room_code

      self._rooms[room_code] = new_state
      await self.broadcast_room(room_code)
      return new_state

room_manager = RoomManager()
