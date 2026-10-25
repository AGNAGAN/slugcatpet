"""各品种蜥蜴的品种参数（LizardBreedParams）、地形与连接阻力表（CreatureTemplate）、体色随机。

PathCost 用 (legality, resistance) 元组表示：元组比较即原版 PathCost 的比较（先比合法性再比阻力）。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import NamedTuple

from .rw import clamped_random_variation, hsl2rgb, wrapped_random_variation

# AItile.Accessibility，顺序即原版枚举序（比较大小时用）
OFFSCREEN = "OffScreen"
FLOOR = "Floor"
CURVED_FLOOR = "CurvedFloor"
CORRIDOR = "Corridor"
CLIMB = "Climb"
WALL = "Wall"
CEILING = "Ceiling"
AIR = "Air"
SOLID = "Solid"
SAND = "Sand"
ACC_NAMES = (OFFSCREEN, FLOOR, CURVED_FLOOR, CORRIDOR, CLIMB, WALL, CEILING, AIR, SOLID, SAND)
ACC_INDEX = {n: i for i, n in enumerate(ACC_NAMES)}

# MovementConnection.MovementType（只列蜥蜴世界里出现的）
STANDARD = "Standard"
REACH_OVER_GAP = "ReachOverGap"
REACH_UP = "ReachUp"
DOUBLE_REACH_UP = "DoubleReachUp"
REACH_DOWN = "ReachDown"
SEMI_DIAGONAL_REACH = "SemiDiagonalReach"
DROP_TO_FLOOR = "DropToFloor"
DROP_TO_CLIMB = "DropToClimb"
LIZARD_TURN = "LizardTurn"
CEILING_SLOPE = "CeilingSlope"
OPEN_DIAGONAL = "OpenDiagonal"
MOVEMENT_TYPES = (
    STANDARD,
    REACH_OVER_GAP,
    REACH_UP,
    DOUBLE_REACH_UP,
    REACH_DOWN,
    SEMI_DIAGONAL_REACH,
    DROP_TO_FLOOR,
    DROP_TO_CLIMB,
    LIZARD_TURN,
    CEILING_SLOPE,
    OPEN_DIAGONAL,
)

# PathCost.Legality
ALLOWED = 0
UNWANTED = 1
ILLEGAL_CONNECTION = 2
ILLEGAL_TILE = 3
SOLID_TILE = 4
UNALLOWED = 5


def cost_add(a: tuple[int, float], b: tuple[int, float]) -> tuple[int, float]:
    """PathCost 加法：合法性取大，阻力相加。"""
    return (a[0] if a[0] > b[0] else b[0], a[1] + b[1])


def cost_allowed(c: tuple[int, float]) -> bool:
    return c[0] <= UNWANTED


class SpeedMultiplier(NamedTuple):
    speed: float
    horizontal: float
    up: float
    down: float


def _template_tiles(parent, listing):
    """CreatureTemplate 构造里的地形阻力表：继承父表、覆盖、再把不超过最高可达地形的项压到它的代价以内。"""
    if parent is None:
        t = [(ILLEGAL_TILE, 10.0 * j) for j in range(len(ACC_NAMES))]
        t[ACC_INDEX[SOLID]] = (SOLID_TILE, 100.0)
    else:
        t = list(parent)
    top = 0
    for acc, res, leg in listing:
        i = ACC_INDEX[acc]
        t[i] = (leg, res)
        if leg == ALLOWED and top < i and acc != SAND:
            top = i
    for m in range(top + 1):
        if t[m] > t[top]:
            t[m] = t[top]
    return t


def _template_conns(parent, listing):
    if parent is None:
        c = {m: (ILLEGAL_CONNECTION, 100.0) for m in MOVEMENT_TYPES}
    else:
        c = dict(parent)
    for typ, res, leg in listing:
        c[typ] = (leg, res)
    return c


# StaticWorld.InitStaticWorld 里的蜥蜴祖先模板
_A = ALLOWED
_LIZARD_TILES = _template_tiles(
    None,
    [(OFFSCREEN, 1.0, _A), (FLOOR, 1.0, _A), (CORRIDOR, 1.0, _A), (CURVED_FLOOR, 1.0, _A)],
)
_LIZARD_CONNS = _template_conns(
    None,
    [
        (STANDARD, 1.0, _A),
        (OPEN_DIAGONAL, 3.0, _A),
        (REACH_OVER_GAP, 3.0, _A),
        (REACH_UP, 2.0, _A),
        (DOUBLE_REACH_UP, 2.0, _A),
        (REACH_DOWN, 2.0, _A),
        (SEMI_DIAGONAL_REACH, 2.0, _A),
        (DROP_TO_FLOOR, 20.0, _A),
        (LIZARD_TURN, 10.0, _A),
    ],
)
# CreatureTemplate.SetDoubleReachUpConnectionParams(Floor, Wall, Floor)
_DOUBLE_REACH_UP_PARAMS = (ACC_INDEX[FLOOR], ACC_INDEX[WALL], ACC_INDEX[FLOOR])


@dataclass
class LizardBreedParams:
    key: str = ""
    # 模板层
    body_size: float = 2.0
    meat_points: int = 6
    visual_radius: float = 0.0
    water_vision: float = 0.0
    through_surface_vision: float = 0.0
    movement_based_vision: float = 0.3
    dangerous_to_player: float = 0.0
    base_damage_resistance: float = 0.0
    base_stun_resistance: float = 0.0
    tile_resistances: list = field(default_factory=list)
    connection_resistances: dict = field(default_factory=dict)
    double_reach_up_params: tuple = _DOUBLE_REACH_UP_PARAMS
    # LizardBreedParams
    toughness: float = 0.0
    stun_toughness: float = 0.0
    bite_damage: float = 0.0
    bite_damage_chance: float = 0.0
    aggression_curve_exponent: float = 0.925
    danger: float = 0.0
    bite_delay: int = 0
    base_speed: float = 0.0
    bite_in_front: float = 0.0
    bite_rad_bonus: float = 0.0
    bite_homing_speed: float = 0.0
    bite_chance: float = 0.0
    attempt_bite_radius: float = 0.0
    get_free_bite_chance: float = 0.0
    standard_color: tuple = (1.0, 1.0, 1.0)
    regain_footing_counter: int = 0
    body_mass: float = 0.0
    body_size_fac: float = 1.0
    body_length_fac: float = 1.0
    body_rad_fac: float = 1.0
    pull_down_fac: float = 1.0
    floor_leverage: float = 0.0
    max_muscle_power: float = 0.0
    terrain_speeds: list = field(default_factory=list)
    wiggle_speed: float = 0.0
    wiggle_delay: int = 0
    body_stiffnes: float = 0.0
    swim_speed: float = 0.0
    idle_counter_subtract_when_close_to_idle_pos: int = 0
    head_shield_angle: float = 0.0
    can_exit_lounge: bool = False
    can_exit_lounge_warm_up: bool = False
    find_lounge_direction: float = 0.0
    lounge_distance: float = 0.0
    pre_lounge_crouch: int = 0
    pre_lounge_crouch_movement: float = 0.0
    lounge_speed: float = 0.0
    lounge_propulsion_frames: int = 0
    lounge_maximum_frames: int = 0
    lounge_jumpyness: float = 0.0
    lounge_delay: int = 0
    risk_of_double_lounge_delay: float = 0.0
    post_lounge_stun: int = 0
    lounge_tendensy: float = 0.0
    perfect_vision_angle: float = 0.0
    periferal_vision_angle: float = 0.0
    shake_prey: int = 100
    bite_dominance: float = 0.0
    limb_size: float = 0.0
    limb_thickness: float = 0.0
    step_length: float = 0.0
    lift_feet: float = 0.0
    feet_down: float = 0.0
    no_grip_speed: float = 0.0
    limb_speed: float = 0.0
    limb_quickness: float = 0.0
    limb_grip_delay: int = 0
    smoothen_leg_movement: bool = False
    leg_pair_displacement: float = 0.0
    walk_bob: float = 0.0
    tail_segments: int = 0
    tail_stiffness: float = 0.0
    tail_stiffness_decline: float = 0.0
    tail_length_factor: float = 0.0
    tail_coloration_start: float = 0.0
    tail_coloration_exponent: float = 0.0
    head_size: float = 0.0
    neck_stiffness: float = 0.0
    jaw_open_angle: float = 0.0
    jaw_open_lower_jaw_fac: float = 0.0
    jaw_open_move_jaws_apart: float = 0.0
    head_graphics: list = field(default_factory=list)
    frames_between_look_focus_change: int = 0
    tongue: bool = False
    tongue_attack_range: float = 0.0
    tongue_warm_up: int = 0
    tongue_segments: int = 0
    tongue_chance: float = 0.0
    throw_action: str = "Hiss"
    pickup_action: str = "Bite"
    jump_action: str = ""
    taming_difficulty: float = 1.0

    def terrain_speed(self, acc: str) -> SpeedMultiplier:
        return self.terrain_speeds[ACC_INDEX[acc]]

    def tile_resistance(self, acc: str) -> tuple[int, float]:
        """CreatureTemplate.AccessibilityResistance。"""
        return self.tile_resistances[ACC_INDEX[acc]]

    def connection_resistance(self, typ: str) -> tuple[int, float]:
        """CreatureTemplate.ConnectionResistance。"""
        return self.connection_resistances[typ]

    def tile_allowed(self, acc: str) -> bool:
        return self.tile_resistances[ACC_INDEX[acc]][0] <= UNWANTED


def _default_speeds() -> list:
    return [SpeedMultiplier(0.1, 1.0, 1.0, 1.0) for _ in ACC_NAMES]


def _pink() -> LizardBreedParams:
    sp = _default_speeds()
    sp[ACC_INDEX[FLOOR]] = SpeedMultiplier(1.0, 1.0, 1.0, 1.0)
    sp[ACC_INDEX[CORRIDOR]] = SpeedMultiplier(1.2, 1.0, 0.8, 1.0)
    sp[ACC_INDEX[CLIMB]] = SpeedMultiplier(0.5, 1.0, 0.75, 1.0)
    if sp[ACC_INDEX[CURVED_FLOOR]].speed == 0.1:
        sp[ACC_INDEX[CURVED_FLOOR]] = sp[ACC_INDEX[FLOOR]]
    tiles = _template_tiles(_LIZARD_TILES, [(FLOOR, 1.0, _A), (CORRIDOR, 1.0, _A), (CLIMB, 2.5, _A)])
    conns = _template_conns(_LIZARD_CONNS, [(DROP_TO_CLIMB, 40.0, _A)])
    toughness = 1.0
    stun = 1.0
    danger = 0.45
    return LizardBreedParams(
        key="pink",
        body_size=2.0,
        meat_points=6,
        visual_radius=900.0,
        water_vision=0.4,
        through_surface_vision=0.85,
        movement_based_vision=0.3,
        dangerous_to_player=danger,
        base_damage_resistance=toughness * 2.0,
        base_stun_resistance=stun,
        tile_resistances=tiles,
        connection_resistances=conns,
        bite_delay=12,
        bite_in_front=25.0,
        bite_homing_speed=1.7,
        bite_chance=0.5,
        attempt_bite_radius=80.0,
        get_free_bite_chance=0.65,
        bite_damage=1.0,
        bite_damage_chance=1.0 / 3.0,
        toughness=toughness,
        stun_toughness=stun,
        regain_footing_counter=10,
        base_speed=4.1,
        body_mass=2.1,
        body_size_fac=1.0,
        floor_leverage=0.5,
        max_muscle_power=5.0,
        wiggle_speed=0.5,
        wiggle_delay=15,
        body_stiffnes=0.2,
        swim_speed=0.2,
        idle_counter_subtract_when_close_to_idle_pos=0,
        danger=danger,
        aggression_curve_exponent=0.9,
        head_shield_angle=100.0,
        can_exit_lounge=False,
        can_exit_lounge_warm_up=True,
        find_lounge_direction=0.5,
        lounge_distance=100.0,
        pre_lounge_crouch=25,
        pre_lounge_crouch_movement=-0.2,
        lounge_speed=1.9,
        lounge_maximum_frames=20,
        lounge_propulsion_frames=10,
        lounge_jumpyness=0.5,
        lounge_delay=90,
        risk_of_double_lounge_delay=0.1,
        post_lounge_stun=20,
        lounge_tendensy=0.05,
        perfect_vision_angle=1.0 + (-1.0 - 1.0) * 0.0,
        periferal_vision_angle=1.0 + (-1.0 - 1.0) * (7.0 / 12.0),
        bite_dominance=0.5,
        limb_size=1.0,
        limb_thickness=1.0,
        step_length=0.5,
        lift_feet=0.3,
        feet_down=0.5,
        no_grip_speed=0.1,
        limb_speed=5.0,
        limb_quickness=0.5,
        limb_grip_delay=1,
        smoothen_leg_movement=True,
        leg_pair_displacement=0.2,
        standard_color=(1.0, 0.0, 1.0),
        walk_bob=4.0,
        tail_segments=5,
        tail_stiffness=250.0,
        tail_stiffness_decline=0.2,
        tail_length_factor=1.2,
        tail_coloration_start=0.3,
        tail_coloration_exponent=2.0,
        head_size=1.0,
        neck_stiffness=0.2,
        jaw_open_angle=90.0,
        jaw_open_lower_jaw_fac=2.0 / 3.0,
        jaw_open_move_jaws_apart=23.0,
        head_graphics=[0] * 5,
        frames_between_look_focus_change=80,
        taming_difficulty=1.0,
        terrain_speeds=sp,
    )


def _green() -> LizardBreedParams:
    sp = _default_speeds()
    sp[ACC_INDEX[FLOOR]] = SpeedMultiplier(1.0, 1.0, 0.8, 1.7)
    sp[ACC_INDEX[CORRIDOR]] = SpeedMultiplier(0.8, 1.0, 0.8, 1.7)
    if sp[ACC_INDEX[CURVED_FLOOR]].speed == 0.1:
        sp[ACC_INDEX[CURVED_FLOOR]] = sp[ACC_INDEX[FLOOR]]
    tiles = _template_tiles(_LIZARD_TILES, [(FLOOR, 1.0, _A), (CORRIDOR, 2.0, _A)])
    conns = _template_conns(_LIZARD_CONNS, [(DROP_TO_FLOOR, 40.0, _A), (LIZARD_TURN, 60.0, _A)])
    toughness = 2.5
    stun = 2.5
    danger = 0.45
    return LizardBreedParams(
        key="green",
        body_size=3.0,
        meat_points=8,
        visual_radius=850.0,
        water_vision=0.3,
        through_surface_vision=0.85,
        movement_based_vision=0.7,
        dangerous_to_player=danger,
        base_damage_resistance=toughness * 2.0,
        base_stun_resistance=stun,
        tile_resistances=tiles,
        connection_resistances=conns,
        bite_delay=20,
        bite_in_front=40.0,
        bite_homing_speed=0.7,
        bite_chance=1.0 / 3.0,
        attempt_bite_radius=100.0,
        get_free_bite_chance=0.45,
        bite_damage=2.0,
        bite_damage_chance=0.5,
        toughness=toughness,
        stun_toughness=stun,
        regain_footing_counter=10,
        base_speed=6.7,
        body_mass=7.5,
        body_size_fac=1.2,
        floor_leverage=7.0,
        max_muscle_power=16.0,
        danger=danger,
        aggression_curve_exponent=0.95,
        wiggle_speed=0.0,
        wiggle_delay=55,
        body_stiffnes=0.5,
        swim_speed=0.6,
        idle_counter_subtract_when_close_to_idle_pos=0,
        bite_dominance=0.8,
        head_shield_angle=100.0,
        can_exit_lounge=False,
        can_exit_lounge_warm_up=False,
        find_lounge_direction=0.0,
        lounge_distance=170.0,
        pre_lounge_crouch=50,
        pre_lounge_crouch_movement=-0.3,
        lounge_speed=1.0,
        lounge_maximum_frames=40,
        lounge_propulsion_frames=40,
        lounge_jumpyness=0.0,
        lounge_delay=150,
        risk_of_double_lounge_delay=0.3,
        post_lounge_stun=40,
        lounge_tendensy=1.0,
        perfect_vision_angle=1.0 + (-1.0 - 1.0) * 0.0,
        periferal_vision_angle=1.0 + (-1.0 - 1.0) * (5.0 / 18.0),
        limb_size=1.4,
        limb_thickness=1.0,
        step_length=0.9,
        lift_feet=0.5,
        feet_down=1.0,
        no_grip_speed=0.05,
        limb_speed=3.0,
        limb_quickness=0.3,
        limb_grip_delay=1,
        smoothen_leg_movement=False,
        leg_pair_displacement=1.0,
        standard_color=(0.2, 1.0, 0.0),
        walk_bob=4.0,
        tail_segments=7,
        tail_stiffness=300.0,
        tail_stiffness_decline=0.6,
        tail_length_factor=0.9,
        tail_coloration_start=0.05,
        tail_coloration_exponent=4.0,
        head_size=1.0,
        neck_stiffness=1.0,
        jaw_open_angle=50.0,
        jaw_open_lower_jaw_fac=0.5,
        jaw_open_move_jaws_apart=14.0,
        head_graphics=[1, 1, 1, 1, 1],
        frames_between_look_focus_change=160,
        taming_difficulty=0.8,
        jump_action="Lunge",
        terrain_speeds=sp,
    )


def _cyan() -> LizardBreedParams:
    sp = _default_speeds()
    sp[ACC_INDEX[FLOOR]] = SpeedMultiplier(1.0, 1.0, 1.0, 1.0)
    sp[ACC_INDEX[CORRIDOR]] = SpeedMultiplier(1.0, 1.0, 1.0, 1.0)
    sp[ACC_INDEX[CLIMB]] = SpeedMultiplier(1.0, 1.0, 1.0, 1.0)
    sp[ACC_INDEX[WALL]] = SpeedMultiplier(0.8, 1.0, 1.0, 1.0)
    sp[ACC_INDEX[CEILING]] = SpeedMultiplier(0.6, 1.0, 1.0, 1.0)
    if sp[ACC_INDEX[CURVED_FLOOR]].speed == 0.1:
        sp[ACC_INDEX[CURVED_FLOOR]] = sp[ACC_INDEX[FLOOR]]
    tiles = _template_tiles(
        _LIZARD_TILES,
        [(FLOOR, 1.0, _A), (CORRIDOR, 1.2, _A), (CLIMB, 0.8, _A), (WALL, 1.0, _A), (CEILING, 1.2, _A)],
    )
    conns = _template_conns(
        _LIZARD_CONNS,
        [
            (DROP_TO_FLOOR, 2.0, _A),
            (DROP_TO_CLIMB, 2.0, _A),
            (REACH_OVER_GAP, 1.1, _A),
            (REACH_UP, 1.1, _A),
            (REACH_DOWN, 1.1, _A),
            (CEILING_SLOPE, 2.0, _A),
        ],
    )
    toughness = 0.9
    stun = 0.9
    danger = 0.65
    return LizardBreedParams(
        key="cyan",
        body_size=2.0,
        meat_points=6,
        visual_radius=990.0,
        water_vision=0.4,
        through_surface_vision=0.85,
        movement_based_vision=0.3,
        dangerous_to_player=danger,
        base_damage_resistance=toughness * 2.0,
        base_stun_resistance=stun,
        tile_resistances=tiles,
        connection_resistances=conns,
        bite_delay=12,
        bite_in_front=25.0,
        bite_homing_speed=1.4,
        bite_chance=0.46511626,
        attempt_bite_radius=90.0,
        get_free_bite_chance=0.72,
        bite_damage=1.0,
        bite_damage_chance=1.0 / 3.0,
        toughness=toughness,
        stun_toughness=stun,
        regain_footing_counter=3,
        base_speed=4.85,
        body_mass=2.0,
        body_size_fac=1.0,
        floor_leverage=0.5,
        max_muscle_power=4.0,
        danger=danger,
        aggression_curve_exponent=0.9,
        wiggle_speed=1.0,
        wiggle_delay=15,
        body_stiffnes=0.0,
        swim_speed=0.45,
        idle_counter_subtract_when_close_to_idle_pos=1,
        head_shield_angle=35.0,
        can_exit_lounge=True,
        can_exit_lounge_warm_up=True,
        find_lounge_direction=1.0,
        lounge_distance=130.0,
        pre_lounge_crouch=35,
        pre_lounge_crouch_movement=-0.3,
        lounge_speed=4.5,
        lounge_maximum_frames=20,
        lounge_propulsion_frames=10,
        lounge_jumpyness=0.9,
        lounge_delay=110,
        risk_of_double_lounge_delay=0.8,
        post_lounge_stun=10,
        lounge_tendensy=1.0 / 30.0,
        perfect_vision_angle=1.0 + (-1.0 - 1.0) * (1.0 / 12.0),
        periferal_vision_angle=1.0 + (-1.0 - 1.0) * (11.0 / 24.0),
        bite_dominance=0.3,
        limb_size=1.0,
        limb_thickness=1.0,
        step_length=0.4,
        lift_feet=0.0,
        feet_down=0.0,
        no_grip_speed=0.2,
        limb_speed=6.0,
        limb_quickness=0.6,
        limb_grip_delay=1,
        smoothen_leg_movement=True,
        leg_pair_displacement=0.0,
        standard_color=(0.0, 1.0, 0.9),
        walk_bob=2.0,
        tail_segments=6,
        tail_stiffness=250.0,
        tail_stiffness_decline=0.2,
        tail_length_factor=1.8,
        tail_coloration_start=0.3,
        tail_coloration_exponent=2.0,
        head_size=0.95,
        neck_stiffness=0.8,
        jaw_open_angle=110.0,
        jaw_open_lower_jaw_fac=0.55,
        jaw_open_move_jaws_apart=22.0,
        head_graphics=[0] * 5,
        frames_between_look_focus_change=80,
        tongue=True,
        tongue_attack_range=160.0,
        tongue_warm_up=8,
        tongue_segments=7,
        tongue_chance=1.0 / 3.0,
        taming_difficulty=1.0,
        throw_action="Launch",
        jump_action="Tongue",
        terrain_speeds=sp,
    )


def _blue() -> LizardBreedParams:
    sp = _default_speeds()
    sp[ACC_INDEX[FLOOR]] = SpeedMultiplier(1.0, 1.0, 1.0, 1.0)
    sp[ACC_INDEX[CORRIDOR]] = SpeedMultiplier(1.0, 1.0, 1.0, 1.0)
    sp[ACC_INDEX[CLIMB]] = SpeedMultiplier(1.0, 1.0, 1.0, 1.0)
    sp[ACC_INDEX[WALL]] = SpeedMultiplier(0.8, 1.0, 1.0, 1.0)
    sp[ACC_INDEX[CEILING]] = SpeedMultiplier(0.6, 1.0, 1.0, 1.0)
    if sp[ACC_INDEX[CURVED_FLOOR]].speed == 0.1:
        sp[ACC_INDEX[CURVED_FLOOR]] = sp[ACC_INDEX[FLOOR]]
    tiles = _template_tiles(
        _LIZARD_TILES,
        [(FLOOR, 1.0, _A), (CORRIDOR, 1.2, _A), (CLIMB, 0.8, _A), (WALL, 1.0, _A), (CEILING, 1.2, _A)],
    )
    conns = _template_conns(
        _LIZARD_CONNS,
        [
            (DROP_TO_FLOOR, 20.0, _A),
            (DROP_TO_CLIMB, 2.0, _A),
            (REACH_OVER_GAP, 1.1, _A),
            (REACH_UP, 1.1, _A),
            (REACH_DOWN, 1.1, _A),
            (CEILING_SLOPE, 2.0, _A),
        ],
    )
    toughness = 0.5
    stun = 0.5
    danger = 0.35
    return LizardBreedParams(
        key="blue",
        body_size=2.0,
        meat_points=5,
        visual_radius=950.0,
        water_vision=0.4,
        through_surface_vision=0.85,
        movement_based_vision=0.3,
        dangerous_to_player=danger,
        base_damage_resistance=toughness * 2.0,
        base_stun_resistance=stun,
        tile_resistances=tiles,
        connection_resistances=conns,
        bite_delay=14,
        bite_in_front=20.0,
        bite_homing_speed=1.4,
        bite_chance=0.4,
        attempt_bite_radius=90.0,
        get_free_bite_chance=0.5,
        bite_damage=0.7,
        bite_damage_chance=0.2,
        toughness=toughness,
        stun_toughness=stun,
        regain_footing_counter=4,
        base_speed=3.2,
        body_mass=1.4,
        body_size_fac=0.9,
        floor_leverage=1.0,
        max_muscle_power=2.0,
        danger=danger,
        aggression_curve_exponent=0.875,
        wiggle_speed=1.0,
        wiggle_delay=15,
        body_stiffnes=0.0,
        swim_speed=0.35,
        idle_counter_subtract_when_close_to_idle_pos=0,
        head_shield_angle=100.0,
        can_exit_lounge=True,
        can_exit_lounge_warm_up=True,
        find_lounge_direction=1.0,
        lounge_distance=80.0,
        pre_lounge_crouch=35,
        pre_lounge_crouch_movement=-0.3,
        lounge_speed=2.5,
        lounge_maximum_frames=20,
        lounge_propulsion_frames=8,
        lounge_jumpyness=0.9,
        lounge_delay=310,
        risk_of_double_lounge_delay=0.8,
        post_lounge_stun=20,
        lounge_tendensy=0.01,
        perfect_vision_angle=1.0 + (-1.0 - 1.0) * (1.0 / 18.0),
        periferal_vision_angle=1.0 + (-1.0 - 1.0) * (11.0 / 24.0),
        bite_dominance=0.1,
        limb_size=0.9,
        limb_thickness=1.0,
        step_length=0.4,
        lift_feet=0.0,
        feet_down=0.0,
        no_grip_speed=0.2,
        limb_speed=6.0,
        limb_quickness=0.6,
        limb_grip_delay=1,
        smoothen_leg_movement=True,
        leg_pair_displacement=0.0,
        standard_color=(0.0, 0.5, 1.0),
        walk_bob=0.4,
        tail_segments=4,
        tail_stiffness=400.0,
        tail_stiffness_decline=0.1,
        tail_length_factor=1.0,
        tail_coloration_start=0.1,
        tail_coloration_exponent=1.2,
        head_size=0.9,
        neck_stiffness=0.0,
        jaw_open_angle=105.0,
        jaw_open_lower_jaw_fac=0.55,
        jaw_open_move_jaws_apart=20.0,
        head_graphics=[0] * 5,
        frames_between_look_focus_change=20,
        tongue=True,
        tongue_attack_range=140.0,
        tongue_warm_up=10,
        tongue_segments=5,
        tongue_chance=0.25,
        taming_difficulty=1.1,
        jump_action="Tongue",
        terrain_speeds=sp,
    )


def _white() -> LizardBreedParams:
    sp = _default_speeds()
    sp[ACC_INDEX[FLOOR]] = SpeedMultiplier(1.0, 1.0, 1.0, 1.0)
    sp[ACC_INDEX[CORRIDOR]] = SpeedMultiplier(1.0, 1.0, 1.0, 1.0)
    sp[ACC_INDEX[CLIMB]] = SpeedMultiplier(1.0, 1.0, 1.0, 1.0)
    sp[ACC_INDEX[WALL]] = SpeedMultiplier(1.0, 1.0, 1.0, 1.0)
    if sp[ACC_INDEX[CURVED_FLOOR]].speed == 0.1:
        sp[ACC_INDEX[CURVED_FLOOR]] = sp[ACC_INDEX[FLOOR]]
    tiles = _template_tiles(
        _LIZARD_TILES, [(FLOOR, 1.0, _A), (CORRIDOR, 1.2, _A), (CLIMB, 0.8, _A), (WALL, 1.0, _A)]
    )
    conns = _template_conns(
        _LIZARD_CONNS,
        [
            (DROP_TO_FLOOR, 10.0, _A),
            (DROP_TO_CLIMB, 10.0, _A),
            (REACH_OVER_GAP, 1.1, _A),
            (REACH_UP, 1.1, _A),
            (REACH_DOWN, 1.1, _A),
            (CEILING_SLOPE, 20.0, _A),
        ],
    )
    toughness = 0.9
    stun = 0.9
    danger = 0.5
    return LizardBreedParams(
        key="white",
        body_size=2.0,
        meat_points=6,
        visual_radius=1300.0,
        water_vision=0.4,
        through_surface_vision=0.9,
        movement_based_vision=0.3,
        dangerous_to_player=danger,
        base_damage_resistance=toughness * 2.0,
        base_stun_resistance=stun,
        tile_resistances=tiles,
        connection_resistances=conns,
        bite_delay=15,
        bite_in_front=25.0,
        bite_homing_speed=1.7,
        bite_chance=0.5,
        attempt_bite_radius=85.0,
        get_free_bite_chance=0.7,
        bite_damage=1.0,
        bite_damage_chance=0.2857143,
        toughness=toughness,
        stun_toughness=stun,
        regain_footing_counter=5,
        base_speed=3.8,
        body_mass=2.1,
        body_size_fac=1.0,
        floor_leverage=0.3,
        max_muscle_power=5.0,
        danger=danger,
        aggression_curve_exponent=0.95,
        wiggle_speed=0.5,
        wiggle_delay=15,
        body_stiffnes=0.15,
        swim_speed=0.25,
        idle_counter_subtract_when_close_to_idle_pos=0,
        head_shield_angle=100.0,
        can_exit_lounge=False,
        can_exit_lounge_warm_up=True,
        find_lounge_direction=0.5,
        lounge_distance=100.0,
        pre_lounge_crouch=25,
        pre_lounge_crouch_movement=-0.2,
        lounge_speed=1.9,
        lounge_maximum_frames=20,
        lounge_propulsion_frames=10,
        lounge_jumpyness=0.5,
        lounge_delay=90,
        risk_of_double_lounge_delay=0.1,
        post_lounge_stun=20,
        lounge_tendensy=0.05,
        perfect_vision_angle=1.0 + (-1.0 - 1.0) * (1.0 / 6.0),
        periferal_vision_angle=1.0 + (-1.0 - 1.0) * (19.0 / 36.0),
        bite_dominance=0.5,
        limb_size=1.0,
        limb_thickness=1.0,
        step_length=0.6,
        lift_feet=0.2,
        feet_down=0.05,
        no_grip_speed=0.1,
        limb_speed=8.0,
        limb_quickness=0.8,
        limb_grip_delay=1,
        smoothen_leg_movement=False,
        leg_pair_displacement=0.0,
        standard_color=(1.0, 1.0, 1.0),
        walk_bob=0.8,
        tail_segments=5,
        tail_stiffness=800.0,
        tail_stiffness_decline=0.1,
        tail_length_factor=1.2,
        tail_coloration_start=0.1,
        tail_coloration_exponent=1.2,
        head_size=1.0,
        neck_stiffness=0.05,
        jaw_open_angle=110.0,
        jaw_open_lower_jaw_fac=0.5,
        jaw_open_move_jaws_apart=23.0,
        head_graphics=[0, 0, 0, 0, 3],
        frames_between_look_focus_change=180,
        taming_difficulty=3.0,
        tongue=True,
        tongue_attack_range=440.0,
        tongue_warm_up=80,
        tongue_segments=10,
        tongue_chance=0.1,
        throw_action="Camouflage",
        jump_action="Tongue",
        terrain_speeds=sp,
    )


def _red() -> LizardBreedParams:
    """MMF 的 Alpha 红蜥蜴按默认关闭取值：biteRadBonus 25、没有舌头。"""
    sp = _default_speeds()
    sp[ACC_INDEX[FLOOR]] = SpeedMultiplier(1.0, 1.0, 1.0, 1.0)
    sp[ACC_INDEX[CORRIDOR]] = SpeedMultiplier(1.0, 1.0, 0.9, 1.0)
    sp[ACC_INDEX[CLIMB]] = SpeedMultiplier(0.9, 1.0, 0.6, 1.0)
    if sp[ACC_INDEX[CURVED_FLOOR]].speed == 0.1:
        sp[ACC_INDEX[CURVED_FLOOR]] = sp[ACC_INDEX[FLOOR]]
    tiles = _template_tiles(_LIZARD_TILES, [(FLOOR, 1.0, _A), (CORRIDOR, 1.0, _A), (CLIMB, 1.0, _A)])
    conns = _template_conns(_LIZARD_CONNS, [(DROP_TO_CLIMB, 4.0, _A)])
    toughness = 3.0
    stun = 3.0
    danger = 0.8
    return LizardBreedParams(
        key="red",
        body_size=3.0,
        meat_points=9,
        visual_radius=2300.0,
        water_vision=0.7,
        through_surface_vision=0.95,
        movement_based_vision=0.3,
        dangerous_to_player=danger,
        base_damage_resistance=toughness * 2.0,
        base_stun_resistance=stun,
        tile_resistances=tiles,
        connection_resistances=conns,
        bite_delay=2,
        bite_in_front=20.0,
        bite_rad_bonus=25.0,
        bite_homing_speed=4.7,
        bite_chance=1.0,
        attempt_bite_radius=120.0,
        get_free_bite_chance=1.0,
        bite_damage=4.0,
        bite_damage_chance=1.0,
        toughness=toughness,
        stun_toughness=stun,
        regain_footing_counter=1,
        base_speed=5.0,
        body_mass=3.1,
        body_size_fac=1.2,
        floor_leverage=6.0,
        max_muscle_power=9.0,
        danger=danger,
        aggression_curve_exponent=0.7,
        wiggle_speed=0.5,
        wiggle_delay=15,
        body_stiffnes=0.3,
        swim_speed=1.9,
        idle_counter_subtract_when_close_to_idle_pos=10,
        head_shield_angle=100.0,
        can_exit_lounge=False,
        can_exit_lounge_warm_up=True,
        find_lounge_direction=0.5,
        lounge_distance=100.0,
        pre_lounge_crouch=25,
        pre_lounge_crouch_movement=-0.2,
        lounge_speed=1.9,
        lounge_maximum_frames=20,
        lounge_propulsion_frames=10,
        lounge_jumpyness=0.5,
        lounge_delay=90,
        risk_of_double_lounge_delay=0.1,
        post_lounge_stun=20,
        lounge_tendensy=0.05,
        perfect_vision_angle=1.0 + (-1.0 - 1.0) * (4.0 / 9.0),
        periferal_vision_angle=1.0 + (-1.0 - 1.0) * (7.0 / 9.0),
        bite_dominance=1.0,
        limb_size=1.5,
        limb_thickness=1.0,
        step_length=0.8,
        lift_feet=0.3,
        feet_down=0.5,
        no_grip_speed=0.25,
        limb_speed=9.0,
        limb_quickness=0.8,
        limb_grip_delay=1,
        smoothen_leg_movement=True,
        leg_pair_displacement=0.2,
        standard_color=(1.0, 0.0, 0.0),
        walk_bob=3.0,
        tail_segments=11,
        tail_stiffness=200.0,
        tail_stiffness_decline=0.3,
        tail_length_factor=1.9,
        tail_coloration_start=0.3,
        tail_coloration_exponent=2.0,
        head_size=1.2,
        neck_stiffness=0.2,
        jaw_open_angle=140.0,
        jaw_open_lower_jaw_fac=2.0 / 3.0,
        jaw_open_move_jaws_apart=23.0,
        head_graphics=[0] * 5,
        frames_between_look_focus_change=20,
        taming_difficulty=7.0,
        throw_action="Spit",
        terrain_speeds=sp,
    )


BREEDS = {
    "green": _green(),
    "pink": _pink(),
    "cyan": _cyan(),
    "blue": _blue(),
    "white": _white(),
    "red": _red(),
}


def get(key: str) -> LizardBreedParams:
    return BREEDS[key]


def effect_color(key: str, rng: random.Random) -> tuple[float, float, float]:
    """Lizard 构造函数里的 effectColor：色相绕圈随机，亮度夹在 0..1。"""
    if key == "white":
        return BREEDS[key].standard_color
    hue_base, hue_dev = {
        "pink": (0.87, 0.1),
        "green": (0.32, 0.1),
        "cyan": (0.49, 0.04),
        "blue": (0.57, 0.08),
        "red": (0.0025, 0.02),
    }[key]
    h = wrapped_random_variation(rng, hue_base, hue_dev, 0.6)
    lum = clamped_random_variation(rng, 0.5, 0.15, 0.1)
    return hsl2rgb(h, 1.0, lum)
