from gomoku.board import Board
from gomoku.constants import BLACK


def test_overline_forbidden():
    board = Board()
    row = 7
    for col in range(3, 8):
        board.set(row, col, BLACK)
    assert board.is_forbidden_move(row, 8)


def test_double_four_forbidden():
    board = Board()
    for col in (4, 5, 6):
        board.set(7, col, BLACK)
    for row in (4, 5, 6):
        board.set(row, 7, BLACK)
    assert board.is_forbidden_move(7, 7)


def test_double_three_forbidden():
    board = Board()
    for col in (5, 6):
        board.set(7, col, BLACK)
    for row in (5, 6):
        board.set(row, 7, BLACK)
    assert board.is_forbidden_move(7, 7)
