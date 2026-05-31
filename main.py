"""Основной файл FastAPI приложения с поддержкой HTML-шаблонов."""
import json
import random
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from enums import GameStatus, CardSuit
from schemas import GameState, Player, Card
from requests import PlayerActionRequest
from game_logic import handle_player_action, get_masked_game_state
from sse_manager import sse_manager

app = FastAPI()
templates = Jinja2Templates(directory="templates")

def start_new_game() -> GameState:
    """Генерирует чистый стартовый стейт игры со случайными картами."""
    suits = list(CardSuit)
    p1_cards = [Card(rank=random.randint(2, 14), suit=random.choice(suits)) for _ in range(2)]
    p2_cards = [Card(rank=random.randint(2, 14), suit=random.choice(suits)) for _ in range(2)]

    return GameState(
        room_id="room123",
        status=GameStatus.PLAYING,
        players=[
            Player(id="p1", name="Алексей", cards=p1_cards, last_bid=None, is_eliminated=False),
            Player(id="p2", name="Мария", cards=p2_cards, last_bid=None, is_eliminated=False),
        ],
        current_player_idx=0,
        logs=["Игра началась! Всем раздано по 2 случайные карты."]
    )

demo_state = start_new_game()

async def trigger_state_broadcast(state: GameState) -> None:
    """Вещает актуальное состояние комнат во все открытые вкладки SSE."""
    for player in state.players:
        safe_state = get_masked_game_state(state, player.id)
        payload = f"data: {json.dumps(safe_state, ensure_ascii=False)}\n\n"
        await sse_manager.broadcast_to_player(player.id, payload)

@app.get("/game/{player_id}", response_class=HTMLResponse)
async def get_game_page(request: Request, player_id: str):
    return templates.TemplateResponse("index.html", {"request": request, "player_id": player_id})

@app.get("/api/game/stream/{player_id}")
async def game_stream(player_id: str, request: Request):
    async def event_generator():
        queue = await sse_manager.subscribe(player_id)
        try:
            initial_safe_state = get_masked_game_state(demo_state, player_id)
            yield f"data: {json.dumps(initial_safe_state, ensure_ascii=False)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                data = await queue.get()
                yield data
        finally:
            sse_manager.unsubscribe(player_id, queue)
    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/game/action")
async def make_action(request: PlayerActionRequest):
    global demo_state
    demo_state = handle_player_action(demo_state, request)
    await trigger_state_broadcast(demo_state)
    return {"status": "success"}

@app.post("/api/game/reset")
async def reset_game():
    """Сбрасывает игру и раздает карты заново."""
    global demo_state
    demo_state = start_new_game()
    await trigger_state_broadcast(demo_state)
    return {"status": "reset"}