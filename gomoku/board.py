from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from .constants import BLACK, BOARD_SIZE, COLORS, EMPTY, WHITE

Coordinate = Tuple[int, int]


DIRECTIONS: Tuple[Tuple[int, int], ...] = (
    (1, 0),
    (0, 1),
    (1, 1),
    (1, -1),
)


@dataclass
class MoveResult:
    color: str
    position: Coordinate
    win: bool = False


class Board:
    """Represents a Gomoku board and encapsulates rule checks."""

    def __init__(self, size: int = BOARD_SIZE) -> None:
        self.size = size
        self.grid: List[List[str]] = [[EMPTY for _ in range(size)] for _ in range(size)]

    # Basic helpers -----------------------------------------------------
    def inside(self, row: int, col: int) -> bool:
        return 0 <= row < self.size and 0 <= col < self.size

    def get(self, row: int, col: int) -> str:
        if not self.inside(row, col):
            raise IndexError("Position outside board")
        return self.grid[row][col]

    def is_empty(self, row: int, col: int) -> bool:
        return self.get(row, col) == EMPTY

    def set(self, row: int, col: int, color: str) -> None:
        if color not in COLORS and color != EMPTY:
            raise ValueError(f"Invalid color '{color}'")
        self.grid[row][col] = color

    def reset(self) -> None:
        for row in range(self.size):
            for col in range(self.size):
                self.grid[row][col] = EMPTY

    # Gameplay ----------------------------------------------------------
    def place_stone(self, color: str, row: int, col: int, *, allow_forbidden: bool = False) -> MoveResult:
        if color not in COLORS:
            raise ValueError("Invalid color")
        if not self.inside(row, col):
            raise ValueError("Move outside board")
        if not self.is_empty(row, col):
            raise ValueError("Cell already occupied")
        if color == BLACK and not allow_forbidden and self.is_forbidden_move(row, col):
            raise ValueError("Forbidden move for black")

        self.set(row, col, color)
        win = self.check_win(row, col)
        return MoveResult(color=color, position=(row, col), win=win)

    def remove_stone(self, row: int, col: int) -> None:
        if not self.inside(row, col):
            raise ValueError("Position outside board")
        self.grid[row][col] = EMPTY

    def check_win(self, row: int, col: int) -> bool:
        color = self.get(row, col)
        if color not in COLORS:
            return False
        for dr, dc in DIRECTIONS:
            count = 1 + self._count_direction(row, col, dr, dc, color) + self._count_direction(row, col, -dr, -dc, color)
            if count >= 5:
                return True
        return False

    # Forbidden move detection -----------------------------------------
    def list_forbidden_points(self) -> List[Coordinate]:
        points: List[Coordinate] = []
        for row in range(self.size):
            for col in range(self.size):
                if self.is_empty(row, col) and self.is_forbidden_move(row, col):
                    points.append((row, col))
        return points

    def is_forbidden_move(self, row: int, col: int) -> bool:
        if not self.is_empty(row, col):
            return False
        # Temporarily place the stone to analyze patterns
        self.set(row, col, BLACK)
        try:
            if self._creates_overline(row, col):
                return True
            open_threes = self._count_open_threes(row, col)
            if open_threes >= 2:
                return True
            open_fours = self._count_open_fours(row, col)
            if open_fours >= 2:
                return True
            return False
        finally:
            self.set(row, col, EMPTY)

    # Pattern helpers ---------------------------------------------------
    def _count_direction(self, row: int, col: int, dr: int, dc: int, color: str) -> int:
        count = 0
        r, c = row + dr, col + dc
        while self.inside(r, c) and self.grid[r][c] == color:
            count += 1
            r += dr
            c += dc
        return count

    def _creates_overline(self, row: int, col: int) -> bool:
        for dr, dc in DIRECTIONS:
            total = 1 + self._count_direction(row, col, dr, dc, BLACK) + self._count_direction(row, col, -dr, -dc, BLACK)
            if total > 5:
                return True
        return False

    def _line_values(self, row: int, col: int, dr: int, dc: int, radius: int = 5) -> List[str]:
        values: List[str] = []
        for offset in range(-radius, radius + 1):
            r = row + offset * dr
            c = col + offset * dc
            if self.inside(r, c):
                values.append(self.grid[r][c])
            else:
                values.append("#")
        return values

    def _count_open_threes(self, row: int, col: int) -> int:
        count = 0
        for dr, dc in DIRECTIONS:
            line = self._line_values(row, col, dr, dc, radius=4)
            count += self._count_open_three_in_line(line)
        return count

    def _count_open_three_in_line(self, line: Sequence[str]) -> int:
        color = BLACK
        total = 0
        length = len(line)
        for start in range(length - 4):
            window = list(line[start : start + 5])
            if "#" in window:
                continue
            if window.count(color) != 3 or window.count(EMPTY) != 2:
                continue
            left_open = start > 0 and line[start - 1] == EMPTY
            right_open = start + 5 < length and line[start + 5] == EMPTY
            if not (left_open and right_open):
                continue
            if self._window_creates_open_four(window, color):
                total += 1
        return total

    def _window_creates_open_four(self, window: Sequence[str], color: str) -> bool:
        for idx, value in enumerate(window):
            if value != EMPTY:
                continue
            mutated = list(window)
            mutated[idx] = color
            if self._is_open_four(mutated, color):
                return True
        return False

    def _is_open_four(self, cells: Sequence[str], color: str) -> bool:
        if len(cells) < 5:
            return False
        for start in range(len(cells) - 3):
            segment = cells[start : start + 4]
            if all(value == color for value in segment):
                left_empty = start == 0 or cells[start - 1] == EMPTY
                right_empty = start + 4 == len(cells) or cells[start + 4] == EMPTY
                if left_empty and right_empty:
                    return True
        return False

    def _count_open_fours(self, row: int, col: int) -> int:
        count = 0
        for dr, dc in DIRECTIONS:
            line = self._line_values(row, col, dr, dc, radius=4)
            count += self._count_open_four_in_line(line)
        return count

    def _count_open_four_in_line(self, line: Sequence[str]) -> int:
        color = BLACK
        total = 0
        length = len(line)
        for start in range(length - 4):
            window = list(line[start : start + 5])
            if "#" in window:
                continue
            if window.count(color) != 4 or window.count(EMPTY) != 1:
                continue
            if self._is_open_four(window, color):
                total += 1
        return total

    # Utilities ---------------------------------------------------------
    def occupied(self) -> Iterable[Coordinate]:
        for row in range(self.size):
            for col in range(self.size):
                if self.grid[row][col] in COLORS:
                    yield (row, col)

    def __str__(self) -> str:
        header = "   " + " ".join(f"{col:2d}" for col in range(self.size))
        rows = [header]
        for idx, line in enumerate(self.grid):
            rows.append(f"{idx:2d} " + "  ".join(line))
        return "\n".join(rows)
