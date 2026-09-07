"""Explicit laboratory selection without reinterpreting any legacy Game."""

from lab_spec import EXPERIMENT_REGISTRY
from varde import Game, get_ruleset_spec


def new_game(n=3, rules="classic", *, experimental=False, research=False, seed=0):
    """Create an allowed game; research controls never become public choices."""
    if type(experimental) is not bool or type(research) is not bool:
        raise ValueError("experimental and research flags must be booleans")
    if not isinstance(rules, str):
        raise ValueError("invalid ruleset")
    if rules in EXPERIMENT_REGISTRY:
        spec = EXPERIMENT_REGISTRY[rules]
        if spec.experimental_availability == "research-only" and not research:
            raise ValueError("static controls require research selection")
        if not (experimental or research):
            raise ValueError("laboratory rules require explicit experimental selection")
        if type(n) is not int or n not in spec.allowed_sizes:
            raise ValueError("invalid laboratory board size")
        from lab_game import LabGame

        if spec.construction.startswith("prebuilt-"):
            return LabGame(n, rules=rules, seed=seed)
        return LabGame(n, rules=rules)

    spec = get_ruleset_spec(rules)
    if not spec.public_new_game and not research:
        raise ValueError("archived rulesets cannot start public games")
    if type(n) is not int or not spec.min_size <= n <= spec.max_size:
        raise ValueError("invalid board size")
    return Game(n, rules=rules)


def load_game(payload):
    """Dispatch by explicit version, retaining the existing version-1 loader."""
    if not isinstance(payload, dict) or type(payload.get("version")) is not int:
        raise ValueError("unsupported Varde snapshot")
    if payload["version"] == 1:
        return Game.from_dict(payload)
    if payload["version"] == 2:
        from lab_game import LabGame

        return LabGame.from_dict(payload)
    raise ValueError("unsupported Varde snapshot version")
