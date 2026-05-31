"""Модуль отвечает за бизнес-логику игры, проверку комбинаций и обработку ходов."""
import random
from collections import Counter
from fastapi import HTTPException
from enums import GameStatus, CombinationType, CardSuit
from requests import PlayerActionRequest, ActionType
from schemas import GameState, Bid, Card

def next_player(state: GameState) -> None:
    """Сдвигает указатель хода на следующего активного игрока."""
    num_players = len(state.players)
    for _ in range(num_players):
        state.current_player_idx = (state.current_player_idx + 1) % num_players
        if not state.players[state.current_player_idx].is_eliminated:
            return

def deal_random_card(player: Player) -> None:
    """Выдает игроку одну случайную карту из стандартной колоды."""
    suits = list(CardSuit)
    rank = random.randint(2, 14)
    suit = random.choice(suits)
    player.cards.append(Card(rank=rank, suit=suit))

def check_combination_on_table(players: list, bid: Bid) -> bool:
    """Проверяет, собрана ли заявленная комбинация из карт ВСЕХ игроков на столе."""
    # Собираем все карты в единый пул
    all_cards = []
    for p in players:
        if not p.is_eliminated:
            all_cards.extend(p.cards)

    ranks = [c.rank for c in all_cards]
    suits = [c.suit for c in all_cards]
    rank_counts = Counter(ranks)
    suit_counts = Counter(suits)

    p_rank = bid.rank_primary
    s_rank = bid.rank_secondary

    if bid.type == CombinationType.HIGH_CARD:
        return rank_counts[p_rank] >= 1

    elif bid.type == CombinationType.PAIR:
        return rank_counts[p_rank] >= 2

    elif bid.type == CombinationType.TWO_PAIRS:
        return rank_counts[p_rank] >= 2 and rank_counts[s_rank] >= 2

    elif bid.type == CombinationType.SET:
        return rank_counts[p_rank] >= 3

    elif bid.type == CombinationType.KARE:
        return rank_counts[p_rank] >= 4

    elif bid.type == CombinationType.FULL_HOUSE:
        # По правилам: достоинство 2ух карт (s_rank) и достоинство 3ёх карт (p_rank)
        return rank_counts[p_rank] >= 3 and rank_counts[s_rank] >= 2

    elif bid.type == CombinationType.STREET:
        # Стрит: последовательность из 5 карт от p_rank до p_rank+4
        for r in range(p_rank, p_rank + 5):
            if rank_counts[r] < 1:
                return False
        return True

    elif bid.type == CombinationType.FLASH:
        # Флеш: 5 карт одной масти, где все карты не ниже p_rank
        valid_cards = [c for c in all_cards if c.rank >= p_rank]
        v_suit_counts = Counter([c.suit for c in valid_cards])
        return any(count >= 5 for count in v_suit_counts.values())

    elif bid.type == CombinationType.STREET_FLASH:
        # Стрит-флеш: стрит заданной масти (или любой масти, если bid.suit не указан)
        target_suits = [bid.suit] if bid.suit else list(CardSuit)
        for suit in target_suits:
            has_suit_street = True
            for r in range(p_rank, p_rank + 5):
                if not any(c.rank == r and c.suit == suit for c in all_cards):
                    has_suit_street = False
                    break
            if has_suit_street:
                return True
        return False

    elif bid.type == CombinationType.FLASH_ROYAL:
        # Флеш-рояль: стрит от 10 до Туза (10,11,12,13,14) одной масти
        target_suits = [bid.suit] if bid.suit else list(CardSuit)
        for suit in target_suits:
            if all(any(c.rank == r and c.suit == suit for c in all_cards) for r in range(10, 15)):
                return True
        return False

    return False

def handle_player_action(state: GameState, request: PlayerActionRequest) -> GameState:
    """Обрабатывает ход игрока, проверяет правила и обновляет состояние игры."""
    if state.status != GameStatus.PLAYING:
        raise HTTPException(status_code=400, detail="Игра сейчас не в активной фазе")

    current_player = state.current_player
    if not current_player or current_player.id != request.player_id:
        raise HTTPException(status_code=403, detail="Сейчас ход другого игрока!")

    # --- ВАРИАНТ 1: ПОВЫШЕНИЕ СТАВКИ ---
    if request.action == ActionType.RAISE:
        if not request.type:
            raise HTTPException(status_code=400, detail="Не указан тип комбинации")

        new_bid = Bid(
            player_id=request.player_id,
            type=request.type,
            rank_primary=request.rank_primary,
            rank_secondary=request.rank_secondary,
            suit=request.suit
        )

        # Проверка валидности ставки против предыдущей
        if not (new_bid > state.last_bid):
            raise HTTPException(status_code=400, detail="Ваша ставка должна быть строго выше предыдущей!")

        state.bid_history.append(new_bid)
        current_player.last_bid = new_bid
        state.logs.append(f"Игрок {current_player.name} заявил комбинацию тип {new_bid.type.name}")
        next_player(state)

    # --- ВАРИАНТ 2: ИГРОК КРИЧИТ "НЕ ВЕРЮ!" ---
    elif request.action == ActionType.CHALLENGE:
        last_bid = state.last_bid
        if not last_bid:
            raise HTTPException(status_code=400, detail="Нельзя сказать 'Не верю' на пустой стол")

        # Находим игрока, чью ставку проверяют
        bluffer = next(p for p in state.players if p.id == last_bid.player_id)
        challenger = current_player

        # Проверяем, существует ли комбинация на самом деле
        combo_exists = check_combination_on_table(state.players, last_bid)

        # Определяем проигравшего раунд
        if combo_exists:
            # Предыдущий игрок сказал правду, проиграл тот, кто не поверил (challenger)
            loser = challenger
            reason = f"Комбинация {last_bid.type.name} реально есть на столе! {challenger.name} получает штрафную карту."
        else:
            # Комбинации нет, предыдущий игрок блефовал и проиграл (bluffer)
            loser = bluffer
            reason = f"Комбинации {last_bid.type.name} нет на столе! {bluffer.name} пойман на блефе и получает штрафную карту."

        # Выдаем карту проигравшему
        deal_random_card(loser)
        state.logs.append(reason)

        # Проверяем выбывание (если карт на руках стало больше 5, например 6 карт)
        if len(loser.cards) >= 6:
            loser.is_eliminated = True
            state.logs.append(f"💥 Игрок {loser.name} набрал 6 карт и ВЫБЫВАЕТ из игры!")

        # Проверяем условия окончания всей игры (должен остаться только 1 не выбывший)
        active_players = [p for p in state.players if not p.is_eliminated]
        if len(active_players) <= 1:
            state.status = GameStatus.GAME_OVER
            winner_name = active_players[0].name if active_players else "Никто"
            state.logs.append(f"🏆 ИГРА ОКОНЧЕНА! Победитель: {winner_name}")
        else:
            # Сбрасываем историю ставок для нового раунда
            state.bid_history = []
            for p in state.players:
                p.last_bid = None

            # Следующий раунд начинает тот, кто проиграл текущий (если он не выбыл)
            if not loser.is_eliminated:
                state.current_player_idx = state.players.index(loser)
            else:
                state.current_player_idx = state.players.index(active_players[0])

    return state

def get_masked_game_state(state: GameState, viewer_id: str) -> dict:
    """Маскирует карты других игроков (превращает их в рубашки) для безопасности передачи по SSE."""
    state_dict = state.model_dump()
    for player in state_dict["players"]:
        if player["id"] != viewer_id and state.status == GameStatus.PLAYING:
            player["cards"] = [{"is_unknown": True} for _ in player["cards"]]
    return state_dict