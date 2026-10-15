"""进入和退出手动控制：复位操控状态，进入时冻结状态机，退出时交还（在 PetUnit.step 里接入）。"""

from __future__ import annotations

from ..planning.climbmap import locate, map_for
from .grasp import GraspControl
from .input import InputBuffer
from .moves_pole import hold
from ..planning.climbmoves import release

POLE_ANIM = {"V": "ClimbOnBeam", "H": "HangFromBeam", "S": "StandOnBeam", "T": "BeamTip"}

# 操控字段 → 默认值，进入和退出时都按它复位，测试会逐项检查
RESET_TABLE: dict[str, object] = {
    "_ctrl_on": False,  # 操控开关
    "_input_provider": None,  # 不摘掉会每 tick 把 _ctrl_on 设回 True
    "_ctrl_input": None,  # 不沿用上次的按键边沿
    "_ctrl_want_jump": 0,  # 免得再次进入的第一帧误跳
    "_ctrl_can_jump": 0,
    "_ctrl_roll_direction": 0,
    "_ctrl_roll_counter": 0,
    "_ctrl_whiplash": False,  # 退出后没人清它
    "_ctrl_rocket_from_belly": False,
    "_ctrl_exit_belly": 0,
    "_ctrl_stop_rolling": 0,
    "_ctrl_super_launch": 0,  # 免得下次进入时带着蓄力
    "_ctrl_sim_hold": 0,
    "_ctrl_sl_decay": 0,
    "_ctrl_slide_direction": 0,  # 免得下次误触急刹翻跳
    "_ctrl_init_slide_counter": 0,
    "_ctrl_slide_counter": 0,
    "_ctrl_skid_cooldown": 0,
    "_ctrl_allow_roll": 0,  # 免得再次进入的第一帧误触落地翻滚
    "_ctrl_consistent_dd": 0,
    "_ctrl_fall_speed": 0.0,
    "_ctrl_prev_floor": True,
    "_ctrl_lower_on_ground": 0,  # 免得再次进入时误触 StandUp / DownOnFours
    "_ctrl_upper_off_ground": 0,
    "_ctrl_crawl_turn_delay": 0,
    "_ctrl_pyro": None,  # 工匠的操控钩子，其他猫为 None
    "_ctrl_pyro_jumped": False,  # 与 PYRO_DEFAULTS 同步
    "_ctrl_pyro_counter": 0,
    "_ctrl_pyro_cooldown": 0.0,
    "_ctrl_pyro_parry_cd": 0.0,
    "_ctrl_tongue": None,  # 圣徒的舌头操控，其他猫为 None
    "_ctrl_bars": None,  # 当前的杆网
    "_ctrl_bar": None,  # 抓着的杆
    "_ctrl_pull": None,  # 翻上横杆的过程
    "_ctrl_slide_up": 0,
    "_ctrl_nograb": 0,
    "_ctrl_was_zerog": False,
}

# 退出时要清掉的手动控制动画，不含 ZeroGPoleGrab
ANIM_RESET = frozenset(("Roll", "Flip", "BellySlide", "RocketJump", "CrawlTurn", "StandUp", "DownOnFours"))


def reset_ctrl_state(body) -> None:
    for k, v in RESET_TABLE.items():
        setattr(body, k, v)


def enter_control(pet, provider) -> None:
    body = pet.body
    beh = pet.behavior
    held = _pole_held(pet)
    if beh is not None:
        beh._break_active_controllers()
        beh.grab.force_release()
    body.stop_walk()
    body.walk_speed_target = None
    body.zerog_pole = None  # 状态机冻结后没人负责松杆
    pet.gfx.sleeping = False
    body.sleeping = False
    pet.gfx.look_at = None
    if beh is not None:
        # 直接设状态再 _enter：_transition 遇到同名状态会直接返回
        beh.state = "IdleStand"
        beh.timer = 0
        beh.phase = 0
        beh._enter("IdleStand")
    reset_ctrl_state(body)
    body._ctrl_input = InputBuffer()  # 新的输入历史，不沿用上次的按键
    body._input_provider = provider
    body._ctrl_bars = lambda: map_for(pet).bars
    if held is not None:
        hold(body, *held)
    _mount_species_ctrl(pet, body)
    pet.grasp_ctrl = GraspControl(pet)
    pet.controlled = True


def _pole_held(pet):
    """正抓着的杆和对应动画，不在杆上时返回 None。"""
    if not pet.body.on_pole:
        return None
    cm = map_for(pet)
    spot = locate(cm, pet)
    if spot is None or spot[0] not in POLE_ANIM:
        return None
    return cm.bars[spot[1]], POLE_ANIM[spot[0]]


def _mount_species_ctrl(pet, body) -> None:
    for ab in getattr(pet, "abilities", {}).values():
        ab.control(pet, body)


def exit_control(pet) -> None:
    if not getattr(pet, "controlled", False):
        return
    body = pet.body
    if getattr(body, "_ctrl_tongue", None) is not None:
        body._ctrl_tongue.leave()
    body._input_provider = None
    body._ctrl_on = False
    reset_ctrl_state(body)
    if body.animation in ANIM_RESET:  # 死后残留 Roll 会让尾钩一直触发
        body.animation = None
    body.stop_walk()
    body.jump_boost = 0.0
    pet.grasp_ctrl = None  # 手里的东西交给 AI 的手部管家
    beh = pet.behavior
    if beh is not None:
        if body.dead:
            pass
        elif body.stun > 0:
            # 强制进入 Stunned，以防当前不在这个状态
            beh.state = "Stunned"
            beh.timer = 0
            beh.phase = 0
            beh._enter("Stunned")
        else:
            # 强制进入，避开 _transition 的同名返回；抓着杆就交给爬架
            if body.on_pole and "Perch" in beh._states:
                st = "Perch"
            else:
                if body.on_pole:
                    release(body)
                st = "IdleStand" if body.on_floor() else "Airborne"
            beh.state = st
            beh.timer = 0
            beh.phase = 0
            beh._enter(st)
    pet.controlled = False
