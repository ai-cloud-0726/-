from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

from .board import Board
from .constants import (
    BLACK,
    EMPTY,
    MAX_SKILL_SLOTS,
    MAX_TURNS_WITHOUT_SKILL,
    SKILL_PROBABILITY_INCREMENT,
    WHITE,
)
from .player import PlayerState
from .skills import SKILL_LIBRARY, SkillDefinition

Coordinate = Tuple[int, int]


ShieldPrompt = Callable[[PlayerState, SkillDefinition, PlayerState], bool]


@dataclass
class Scoreboard:
    black_wins: int = 0
    white_wins: int = 0
    draws: int = 0

    def record_win(self, color: str) -> None:
        if color == BLACK:
            self.black_wins += 1
        else:
            self.white_wins += 1

    def record_draw(self) -> None:
        self.draws += 1


@dataclass
class Game:
    board: Board = field(default_factory=Board)
    rng: random.Random = field(default_factory=random.Random)
    shield_prompt: Optional[ShieldPrompt] = None

    def __post_init__(self) -> None:
        self.players: List[PlayerState] = [
            PlayerState(name="Black", color=BLACK),
            PlayerState(name="White", color=WHITE),
        ]
        self.current_index: int = 0
        self.round_active: bool = False
        self.scoreboard = Scoreboard()
        self.log: List[str] = []

    # Setup -------------------------------------------------------------
    def start_round(self) -> None:
        self.board.reset()
        self.round_active = True
        self.current_index = 0
        self.log.clear()
        for player in self.players:
            player.skills = [None] * MAX_SKILL_SLOTS
            player.turns_without_skill = 0
            self._award_random_skill(player)
        self.log.append("Round started")

    # Accessors ---------------------------------------------------------
    @property
    def current_player(self) -> PlayerState:
        return self.players[self.current_index]

    def get_opponent(self, player: PlayerState) -> PlayerState:
        return self.players[1] if player is self.players[0] else self.players[0]

    # Gameplay ----------------------------------------------------------
    def place_stone(self, row: int, col: int) -> None:
        self._ensure_round_active()
        player = self.current_player
        result = self.board.place_stone(player.color, row, col)
        self.log.append(f"{player.name} placed at ({row}, {col})")
        if result.win:
            self._complete_round(player, f"Five in a row from move at ({row}, {col})")
            return
        if all(self.board.get(r, c) != EMPTY for r in range(self.board.size) for c in range(self.board.size)):
            self.declare_draw("Board filled")
            return
        self._after_action(player)
        self._advance_turn()

    def use_skill(self, slot_index: int, target: Optional[Sequence[int]] = None) -> None:
        self._ensure_round_active()
        player = self.current_player
        if not 0 <= slot_index < len(player.skills):
            raise IndexError("Invalid skill slot")
        skill = player.skills[slot_index]
        if skill is None:
            raise ValueError("Selected slot is empty")
        if skill.reactive:
            raise ValueError("Reactive skills cannot be used manually")

        opponent = self.get_opponent(player)
        # Consume skill now but allow rollback on error
        player.skills[slot_index] = None
        try:
            coordinate: Optional[Tuple[int, int]] = None
            if target is not None:
                if len(target) != 2:
                    raise ValueError("Target must contain two coordinates")
                coordinate = (int(target[0]), int(target[1]))
            if opponent.has_shield():
                if self._should_use_shield(opponent, skill, player):
                    opponent.remove_shield()
                    self.log.append(
                        f"{opponent.name} blocked {player.name}'s {skill.name}"
                    )
                    self._after_action(player)
                    self._advance_turn()
                    return
            message, affected = skill.activate(
                self,
                player,
                target=coordinate,
            )
            self.log.append(message)
            if not self.round_active:
                # Skill may have ended the round (Flip Table)
                return
            if self._check_skill_victory(player, opponent, affected):
                return
            self._after_action(player)
            self._advance_turn()
        except Exception as exc:
            # Rollback: return skill to slot before propagating error
            player.skills[slot_index] = skill
            raise exc

    def declare_draw(self, reason: str) -> None:
        if not self.round_active:
            return
        self.round_active = False
        self.scoreboard.record_draw()
        self.log.append(f"Round ended in a draw: {reason}")

    # Internal helpers --------------------------------------------------
    def _after_action(self, player: PlayerState) -> None:
        player.turns_without_skill += 1
        if player.available_skill_slots() == 0:
            return
        if player.turns_without_skill >= MAX_TURNS_WITHOUT_SKILL:
            self._award_random_skill(player)
            return
        probability = min(1.0, player.turns_without_skill * SKILL_PROBABILITY_INCREMENT)
        if self.rng.random() < probability:
            self._award_random_skill(player)

    def _award_random_skill(self, player: PlayerState) -> None:
        available = [skill for skill in SKILL_LIBRARY if skill.id != "shield" or not player.has_shield()]
        skill = self.rng.choice(available)
        if not player.add_skill(skill):
            return
        self.log.append(f"{player.name} received skill {skill.name}")

    def _advance_turn(self) -> None:
        self.current_index = 1 - self.current_index

    def _complete_round(self, winner: PlayerState, reason: str) -> None:
        self.round_active = False
        winner.score += 1
        self.scoreboard.record_win(winner.color)
        self.log.append(f"{winner.name} wins: {reason}")

    def _should_use_shield(
        self, defender: PlayerState, incoming_skill: SkillDefinition, attacker: PlayerState
    ) -> bool:
        if self.shield_prompt is None:
            return True
        return self.shield_prompt(defender, incoming_skill, attacker)

    def _check_skill_victory(
        self,
        player: PlayerState,
        opponent: PlayerState,
        affected: Sequence[Coordinate],
    ) -> bool:
        for pos in affected:
            row, col = pos
            color = self.board.get(row, col)
            if color == player.color and self.board.check_win(row, col):
                self._complete_round(player, f"Skill {player.name} created a line")
                return True
            if color == opponent.color and self.board.check_win(row, col):
                self._complete_round(opponent, f"{player.name}'s skill backfired")
                return True
        return False

    def _ensure_round_active(self) -> None:
        if not self.round_active:
            raise RuntimeError("Round has not started. Call start_round() first.")
