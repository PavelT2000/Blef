"""Управление колодой из 52 уникальных карт на всю игру."""
import random

from fastapi import HTTPException

from enums import CardSuit
from schemas import Card, GameState, Player

DECK_SIZE = 52


def create_shuffled_deck() -> list[Card]:
    """Создаёт полную перемешанную колоду (52 карты)."""
    deck = [
        Card(rank=rank, suit=suit)
        for suit in CardSuit
        for rank in range(2, 15)
    ]
    random.shuffle(deck)
    return deck


def init_game_deck(state: GameState) -> None:
    """Сбрасывает колоду: все карты вне рук игроков возвращаются и перемешиваются."""
    state.deck = create_shuffled_deck()


def _draw_from_deck(state: GameState) -> Card:
    if not state.deck:
        raise HTTPException(status_code=400, detail="Колода закончилась")
    return state.deck.pop()


def deal_to_player(state: GameState, player: Player) -> None:
    """Раздаёт одну карту игроку из колоды."""
    player.cards.append(_draw_from_deck(state))


def return_to_deck(state: GameState, cards: list[Card]) -> None:
    """Возвращает карты в колоду (без перемешивания)."""
    state.deck.extend(cards)


def deal_initial_cards(state: GameState) -> None:
    """Раздаёт по одной карте каждому игроку из новой колоды."""
    init_game_deck(state)
    for player in state.players:
        player.cards.clear()
        player.is_eliminated = False
        player.last_bid = None
        deal_to_player(state, player)


def reshuffle_active_hands(state: GameState) -> None:
    """Возвращает карты активных игроков в колоду, тасует и раздаёт заново."""
    hand_sizes: dict[str, int] = {}
    for player in state.players:
        if player.is_eliminated:
            continue
        hand_sizes[player.id] = len(player.cards)
        return_to_deck(state, player.cards)
        player.cards.clear()

    random.shuffle(state.deck)

    for player in state.players:
        if player.is_eliminated:
            continue
        for _ in range(hand_sizes[player.id]):
            deal_to_player(state, player)
