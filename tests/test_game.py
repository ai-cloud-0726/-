import random

from gomoku.constants import WHITE
from gomoku.game import Game
from gomoku.skills import SKILL_BY_ID


def make_game() -> Game:
    return Game(rng=random.Random(0), shield_prompt=lambda *_: False)


def test_start_round_assigns_single_skill_per_player():
    game = make_game()
    game.start_round()
    for player in game.players:
        filled = sum(1 for skill in player.skills if skill is not None)
        assert filled == 1


def test_invert_requires_target():
    game = make_game()
    game.start_round()
    player = game.current_player
    player.skills = [SKILL_BY_ID["invert"], None, None]
    try:
        game.use_skill(0)
    except ValueError:
        # Skill should be restored on failure
        assert player.skills[0] is SKILL_BY_ID["invert"]
    else:
        assert False, "Expected ValueError for missing target"


def test_flip_table_causes_draw():
    game = make_game()
    game.start_round()
    player = game.current_player
    player.skills = [SKILL_BY_ID["flip"], None, None]
    game.use_skill(0)
    assert not game.round_active
    assert game.scoreboard.draws == 1


def test_shield_blocks_skill():
    blocked: list[str] = []

    def use_shield(defender, skill, attacker):
        blocked.append(skill.id)
        return True

    game = Game(rng=random.Random(0), shield_prompt=use_shield)
    game.start_round()
    attacker = game.current_player
    defender = game.get_opponent(attacker)
    game._after_action = lambda player: None  # type: ignore[assignment]
    attacker.skills = [SKILL_BY_ID["swap"], SKILL_BY_ID["flip"], SKILL_BY_ID["invert"]]
    defender.skills = [SKILL_BY_ID["shield"], SKILL_BY_ID["swap"], SKILL_BY_ID["invert"]]
    game.board.set(7, 7, WHITE)
    game.use_skill(0, target=None)
    assert game.board.get(7, 7) == WHITE
    assert not defender.has_shield()
    assert blocked == ["swap"]
    assert game.current_player is defender
