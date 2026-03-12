from __future__ import annotations

import sys
from typing import List

from gomoku.board import Board
from gomoku.constants import BLACK, WHITE
from gomoku.game import Game
from gomoku.player import PlayerState
from gomoku.skills import SkillDefinition


def format_skills(player: PlayerState) -> str:
    parts: List[str] = []
    for idx, skill in enumerate(player.skills):
        if skill is None:
            parts.append(f"[{idx}] 空")
        else:
            suffix = "(被动)" if skill.reactive else ""
            parts.append(f"[{idx}] {skill.name}{suffix}")
    return "  ".join(parts)


def prompt_shield(defender: PlayerState, skill: SkillDefinition, attacker: PlayerState) -> bool:
    while True:
        print(
            f"{defender.name} 拥有无懈可击。是否拦截 {attacker.name} 的 {skill.name}? (y/n)",
            end=" ",
        )
        sys.stdout.flush()
        choice = sys.stdin.readline().strip().lower()
        if choice in {"y", "yes", "是", "使用"}:
            return True
        if choice in {"n", "no", "否", "不用"}:
            return False
        print("请输入 y 或 n。")


def print_board(board: Board) -> None:
    print(board)


def print_status(game: Game) -> None:
    print("=== 状态 ===")
    print(f"当前轮到: {game.current_player.name} ({'黑' if game.current_player.color == BLACK else '白'})")
    print(
        f"比分: 黑方 {game.scoreboard.black_wins} 胜 / 白方 {game.scoreboard.white_wins} 胜 / 平局 {game.scoreboard.draws}"
    )
    for player in game.players:
        print(f"{player.name} 技能栏: {format_skills(player)}")


def list_forbidden(game: Game) -> None:
    points = game.board.list_forbidden_points()
    if not points:
        print("当前无禁手点。")
        return
    formatted = ", ".join(f"({r}, {c})" for r, c in points)
    print(f"禁手点: {formatted}")


def main() -> None:
    game = Game(shield_prompt=prompt_shield)
    print("五子棋技能对战 - Python 版")
    print("输入 help 查看指令。")
    while True:
        try:
            command = input("指令> ").strip()
        except EOFError:
            print()
            break
        if not command:
            continue
        if command == "help":
            print("可用指令:")
            print("  start                - 开始新的一局")
            print("  move r c             - 在 (r, c) 落子")
            print("  skill idx [r c]      - 使用技能，可选目标坐标")
            print("  board                - 查看棋盘")
            print("  status               - 查看比分和技能栏")
            print("  forbidden            - 查看禁手点")
            print("  log                  - 查看事件日志")
            print("  quit                 - 退出")
            continue
        if command == "quit":
            break
        if command == "board":
            print_board(game.board)
            continue
        if command == "status":
            if not game.round_active:
                print("请先 start 开局。")
            print_status(game)
            continue
        if command == "forbidden":
            list_forbidden(game)
            continue
        if command == "log":
            for entry in game.log:
                print(entry)
            continue
        if command == "start":
            game.start_round()
            print("新的一局开始，双方各获随机技能。")
            print_status(game)
            continue
        if command.startswith("move"):
            if not game.round_active:
                print("请先 start 开局。")
                continue
            parts = command.split()
            if len(parts) != 3:
                print("格式: move 行 列")
                continue
            try:
                row = int(parts[1])
                col = int(parts[2])
                game.place_stone(row, col)
            except Exception as exc:
                print(f"落子失败: {exc}")
                continue
            if game.round_active:
                print_status(game)
            else:
                print("本局结束。输入 start 重新开始。")
            continue
        if command.startswith("skill"):
            if not game.round_active:
                print("请先 start 开局。")
                continue
            parts = command.split()
            if len(parts) not in {2, 4}:
                print("格式: skill 槽位 [行 列]")
                continue
            try:
                slot = int(parts[1])
                target = None
                if len(parts) == 4:
                    target = (int(parts[2]), int(parts[3]))
                game.use_skill(slot, target)
            except Exception as exc:
                print(f"技能失败: {exc}")
                continue
            if game.round_active:
                print_status(game)
            else:
                print("本局结束。输入 start 重新开始。")
            continue
        print("未知指令，输入 help 查看帮助。")


if __name__ == "__main__":
    main()
