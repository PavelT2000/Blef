"""Основной файл FastAPI приложения с поддержкой HTML-шаблонов."""

import json
from contextlib import asynccontextmanager



from fastapi import FastAPI, HTTPException, Request

from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates



from enums import GameStatus

from requests import (

    PlayerActionRequest,

    JoinRequest,

    StartGameRequest,

    FinishShowdownRequest,

    LeaveRequest,

    ResetRoomRequest,

)

from game_logic import get_masked_game_state

from config import TURN_TIMEOUT_SECONDS
from room_manager import room_manager, find_player

from sse_manager import sse_manager



@asynccontextmanager
async def lifespan(app: FastAPI):
    room_manager.start_inactivity_cleanup()
    yield
    await room_manager.stop_inactivity_cleanup()


app = FastAPI(
    title="Блеф",
    description="Многопользовательская игра «Блеф»",
    lifespan=lifespan,
)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")





def _http_error(exc: ValueError) -> HTTPException:

    return HTTPException(status_code=400, detail=str(exc))





@app.get("/", response_class=HTMLResponse)

async def home_page(request: Request):

    return templates.TemplateResponse(request, "lobby.html", {"room_code": ""})





@app.get("/join/{room_code}", response_class=HTMLResponse)

async def join_page(request: Request, room_code: str):

    code = room_code.upper()

    if room_manager.get_room(code) is None:

        raise HTTPException(status_code=404, detail="Комната не найдена")

    return templates.TemplateResponse(request, "lobby.html", {"room_code": code})





@app.get("/game/{room_code}/{player_id}", response_class=HTMLResponse)

async def get_game_page(request: Request, room_code: str, player_id: str):

    code = room_code.upper()

    state = room_manager.get_room(code)

    if state is None or find_player(state, player_id) is None:

        raise HTTPException(

            status_code=404,

            detail="Игрок или комната не найдены. Войдите заново с главной страницы.",

        )

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "player_id": player_id,
            "room_code": code,
            "turn_timeout": TURN_TIMEOUT_SECONDS,
        },
    )





@app.post("/api/rooms/create")

async def create_room():

    code, state = await room_manager.create_room()

    return {

        "room_code": code,

        "join_url": f"/join/{code}",

        "players_count": len(state.players),

    }





@app.get("/api/rooms/{room_code}")

async def get_room_info(room_code: str):

    code = room_code.upper()

    state = room_manager.get_room(code)

    if state is None:

        raise HTTPException(status_code=404, detail="Комната не найдена")

    return {

        "room_code": code,

        "status": state.status,

        "players_count": len(state.players),

        "player_names": [p.name for p in state.players],

    }





@app.post("/api/game/join")

async def join_game(request: JoinRequest):

    name = request.name.strip()

    if not name:

        raise HTTPException(status_code=400, detail="Имя не может быть пустым")

    try:

        player, _ = await room_manager.join_room(request.room_code, name)

    except ValueError as exc:

        raise _http_error(exc) from exc



    code = request.room_code.upper()

    return {

        "player_id": player.id,

        "name": player.name,

        "room_code": code,

        "game_url": f"/game/{code}/{player.id}",

    }





@app.post("/api/game/leave")

async def leave_game(request: LeaveRequest):

    code = request.room_code.upper()

    state = await room_manager.remove_player(code, request.player_id)

    if state is None:

        return {"status": "room_closed"}

    return {"status": "left", "room_code": code}





@app.post("/api/game/start")

async def start_game(request: StartGameRequest):

    try:

        await room_manager.start_game(request.room_code, request.player_id)

    except ValueError as exc:

        raise _http_error(exc) from exc

    return {"status": "started"}





@app.get("/api/game/stream/{room_code}/{player_id}")

async def game_stream(room_code: str, player_id: str, request: Request):

    code = room_code.upper()

    state = room_manager.get_room(code)

    if state is None or find_player(state, player_id) is None:

        raise HTTPException(status_code=404, detail="Игрок или комната не найдены")



    async def event_generator():

        queue = await sse_manager.subscribe(player_id)

        try:

            current = room_manager.get_room(code)

            if current:

                initial_safe_state = get_masked_game_state(current, player_id)

                yield f"data: {json.dumps(initial_safe_state, ensure_ascii=False)}\n\n"

            while True:

                if await request.is_disconnected():

                    break

                data = await queue.get()

                yield data

        finally:

            sse_manager.unsubscribe(player_id, queue)



    return StreamingResponse(

        event_generator(),

        media_type="text/event-stream",

        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},

    )





@app.post("/api/game/action")

async def make_action(request: PlayerActionRequest):

    try:

        await room_manager.player_action(request.room_code, request)

    except ValueError as exc:

        raise _http_error(exc) from exc

    return {"status": "success"}





@app.post("/api/game/finish-showdown")

async def finish_showdown(request: FinishShowdownRequest):

    try:

        state = await room_manager.finish_showdown(

            request.room_code, request.player_id

        )

    except ValueError as exc:

        raise _http_error(exc) from exc

    if state.status != GameStatus.SHOWDOWN:

        return {"status": "already_finished"}

    return {"status": "finished"}





@app.post("/api/game/reset")

async def reset_game(request: ResetRoomRequest):

    try:

        await room_manager.reset_room(request.room_code, request.player_id)

    except ValueError as exc:

        raise _http_error(exc) from exc

    return {"status": "reset", "room_code": request.room_code.upper()}

