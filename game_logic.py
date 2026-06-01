"""Модуль отвечает за бизнес-логику игры, проверку комбинаций и обработку ходов."""
from fastapi import HTTPException

from enums import GameStatus
from requests import PlayerActionRequest, ActionType
from bid_comparison import is_bid_stronger
from combination_check import check_combination_on_table
from deck import deal_to_player, reshuffle_active_hands
from schemas import GameState, Bid, Player


def next_player(state: GameState) -> None:
    """Сдвигает указатель хода на следующего активного игрока."""
    num_players = len(state.players)
    for _ in range(num_players):
        state.current_player_idx = (state.current_player_idx + 1) % num_players
        if not state.players[state.current_player_idx].is_eliminated:
            return


def handle_player_action(state: GameState, request: PlayerActionRequest) -> GameState:
    """Обрабатывает ход игрока, проверяет правила и обновляет состояние игры."""
    if state.status != GameStatus.PLAYING:
        raise HTTPException(status_code=400, detail="Игра сейчас не в активной фазе")

    current_player = state.current_player
    if not current_player or current_player.id != request.player_id:
        raise HTTPException(status_code=403, detail="Сейчас ход другого игрока!")

    if request.action == ActionType.RAISE:
        if not request.type:
            raise HTTPException(status_code=400, detail="Не указан тип комбинации")

        new_bid = Bid(
            player_id=request.player_id,
            type=request.type,
            rank_primary=request.rank_primary,
            rank_secondary=request.rank_secondary,
            suit=request.suit,
        )

        if not is_bid_stronger(new_bid, state.last_bid):
            raise HTTPException(
                status_code=400,
                detail="Новая ставка должна быть сильнее предыдущей",
            )

        state.bid_history.append(new_bid)
        current_player.last_bid = new_bid
        state.logs.append(
            f"Игрок {current_player.name} заявил комбинацию {new_bid.type.name}"
        )
        next_player(state)

    elif request.action == ActionType.CHALLENGE:
        last_bid = state.last_bid
        if not last_bid:
            raise HTTPException(status_code=400, detail="Нельзя сказать 'Не верю' на пустой стол")

        bluffer = next(p for p in state.players if p.id == last_bid.player_id)
        challenger = current_player

        combination_exists = check_combination_on_table(state.players, last_bid)

        if combination_exists:
            loser = challenger
        else:
            loser = bluffer

        state.showdown_loser_id = loser.id
        state.showdown_combination_found = combination_exists
        state.showdown_message = (
            f"{challenger.name} сказал «Не верю!» "
            f"Ставка {bluffer.name}: {last_bid.type.name}. "
            f"Комбинация на столе: {'есть' if combination_exists else 'нет'}. "
            f"Проиграл раунд: {loser.name}"
        )
        state.status = GameStatus.SHOWDOWN

    return state


def finalize_showdown(state: GameState) -> GameState:
    """Завершает вскрытие: штрафная карта, выбывание, новый раунд."""
    if state.status != GameStatus.SHOWDOWN or not state.showdown_loser_id:
        return state

    loser = next(p for p in state.players if p.id == state.showdown_loser_id)
    last_bid = state.last_bid
    combination_exists = state.showdown_combination_found or False
    challenger = state.current_player
    bluffer = next((p for p in state.players if p.id == last_bid.player_id), None) if last_bid else None

    deal_to_player(state, loser)

    if challenger and bluffer and last_bid:
        state.logs.append(
            f"{challenger.name} проверил ставку {bluffer.name}: "
            f"{last_bid.type.name}. "
            f"Комбинация на столе: {'да' if combination_exists else 'нет'}. "
            f"Штрафную карту получает {loser.name}."
        )

    limit = state.elimination_limit
    if len(loser.cards) >= limit:
        loser.is_eliminated = True
        state.logs.append(
            f"Игрок {loser.name} набрал {limit} карт и выбывает из игры!"
        )

    state.showdown_loser_id = None
    state.showdown_message = None
    state.showdown_combination_found = None

    active_players = [p for p in state.players if not p.is_eliminated]
    if len(active_players) <= 1:
        state.status = GameStatus.GAME_OVER
        winner_name = active_players[0].name if active_players else "Никто"
        state.logs.append(f"ИГРА ОКОНЧЕНА! Победитель: {winner_name}")
    else:
        reshuffle_active_hands(state)
        state.bid_history = []
        for p in state.players:
            p.last_bid = None

        state.logs.append("Новый раунд: карты перетасованы из колоды.")
        state.status = GameStatus.PLAYING

        if not loser.is_eliminated:
            state.current_player_idx = state.players.index(loser)
        else:
            state.current_player_idx = state.players.index(active_players[0])

    return state


def get_masked_game_state(state: GameState, viewer_id: str) -> dict:
    """Маскирует карты других игроков и скрывает оставшуюся колоду."""
    from config import SHOWDOWN_TIMEOUT_SECONDS, TURN_TIMEOUT_SECONDS, compute_elimination_limit

    state_dict = state.model_dump()
    if state.status == GameStatus.LOBBY:
        active = [p for p in state.players if not p.is_eliminated]
        state_dict["planned_elimination_limit"] = compute_elimination_limit(
            len(active) or len(state.players)
        )
    state_dict["deck_count"] = len(state.deck)
    state_dict["turn_timeout_seconds"] = TURN_TIMEOUT_SECONDS
    state_dict["showdown_timeout_seconds"] = SHOWDOWN_TIMEOUT_SECONDS
    del state_dict["deck"]
    del state_dict["turn_generation"]
    if state.status == GameStatus.PLAYING:
        for player in state_dict["players"]:
            if player["id"] != viewer_id:
                player["cards"] = [{"is_unknown": True} for _ in player["cards"]]
    return state_dict
