from grid2op.Action import DontAct
from grid2op.Reward import FlatReward
from grid2op.Rules import AlwaysLegal
from grid2op.Chronics import ChangeNothing
from grid2op.Backend import PandaPowerBackend

config = {
    "backend": PandaPowerBackend,
    "action_class": DontAct,
    "observation_class": None,
    "reward_class": FlatReward,
    "gamerules_class": AlwaysLegal,
    "chronics_class": ChangeNothing,
    "grid_value_class": None,
    "volagecontroler_class": None,
    "thermal_limits": None,
    "names_chronics_to_grid": None,
}
