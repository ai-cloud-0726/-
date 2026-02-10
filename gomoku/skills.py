from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from .constants import BLACK, EMPTY

if TYPE_CHECKING:
    from .board import Board
    from .game import Game
    from .player import PlayerState

Coordinate = Tuple[int, int]
SkillOutcome = Tuple[str, List[Coordinate]]


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    name: str
    description: str
    requires_target: bool = False
    reactive: bool = False

    def activate(
        self, game: "Game", user: "PlayerState", target: Optional[Coordinate] = None
    ) -> SkillOutcome:
        if self.id == "invert":
            return _invert_stone(game, user, target)
        if self.id == "shift":
            return _shift_line(game, user)
        if self.id == "swap":
            return _swap_random(game, user)
        if self.id == "shield":
            raise ValueError("Shield can only be triggered reactively")
        if self.id == "flip":
            return _flip_table(game, user)
        raise ValueError(f"Unknown skill id {self.id}")


def _validate_target(game: "Game", opponent: "PlayerState", target: Optional[Coordinate]) -> Coordinate:
    if target is None:
        raise ValueError("This skill requires a target coordinate")
    row, col = target
    if not game.board.inside(row, col):
        raise ValueError("Target outside board")
    if game.board.get(row, col) != opponent.color:
        raise ValueError("Targeted cell does not contain an opponent stone")
    return row, col


def _invert_stone(
    game: "Game", user: "PlayerState", target: Optional[Coordinate]
) -> SkillOutcome:
    opponent = game.get_opponent(user)
    row, col = _validate_target(game, opponent, target)
    game.board.set(row, col, user.color)
    return f"{user.name} inverted ({row}, {col}) to their color", [(row, col)]


def _shift_line(game: "Game", user: "PlayerState") -> SkillOutcome:
    opponent = game.get_opponent(user)
    stones = list(game.board.occupied())
    enemy_positions = [pos for pos in stones if game.board.get(*pos) == opponent.color]
    if not enemy_positions:
        raise ValueError("Opponent has no stones to shift")
    random.shuffle(enemy_positions)
    moved: List[Coordinate] = []
    direction = -1 if user.color == BLACK else 1
    for row, col in enemy_positions[:3]:
        target_row = row
        while True:
            next_row = target_row + direction
            if not game.board.inside(next_row, col):
                break
            if game.board.is_empty(next_row, col):
                game.board.set(next_row, col, opponent.color)
                game.board.set(row, col, EMPTY)
                moved.extend([(row, col), (next_row, col)])
                break
            target_row = next_row
        else:
            continue
    if not moved:
        return f"{user.name} tried to shift stones but nothing moved", []
    # Deduplicate coordinates for follow-up checks
    unique_positions = list(dict.fromkeys(moved))
    return f"{user.name} shifted {len(moved) // 2} stones", unique_positions


def _swap_random(game: "Game", user: "PlayerState") -> SkillOutcome:
    opponent = game.get_opponent(user)
    stones = [pos for pos in game.board.occupied() if game.board.get(*pos) == opponent.color]
    if not stones:
        raise ValueError("Opponent has no stones to swap")
    row, col = random.choice(stones)
    game.board.set(row, col, user.color)
    return f"{user.name} swapped a random stone at ({row}, {col})", [(row, col)]


def _flip_table(game: "Game", user: "PlayerState") -> SkillOutcome:
    game.declare_draw(f"{user.name} used Flip Table")
    return f"{user.name} ended the round with a draw", []


SKILL_LIBRARY: Tuple[SkillDefinition, ...] = (
    SkillDefinition(
        id="invert",
        name="颠倒黑白",
        description="将指定的对方棋子转换为己方棋子",
        requires_target=True,
    ),
    SkillDefinition(
        id="shift",
        name="排山倒海",
        description="随机选择对方三枚棋子向其阵营推进一格",
    ),
    SkillDefinition(
        id="swap",
        name="偷梁换柱",
        description="随机将对方的一枚棋子化为己方",
    ),
    SkillDefinition(
        id="shield",
        name="无懈可击",
        description="被动：可选择抵挡一次对方技能",
        reactive=True,
    ),
    SkillDefinition(
        id="flip",
        name="掀桌",
        description="立即宣告本局平局",
    ),
)


SKILL_BY_ID: Dict[str, SkillDefinition] = {skill.id: skill for skill in SKILL_LIBRARY}
