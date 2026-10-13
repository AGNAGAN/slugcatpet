"""SlugStats：每种族的移动因子/体重/饱食/动作冲量数值；DEFAULT_STATS=现值基线。"""

from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class SlugStats:
    runspeed_fac: float = 1.0
    pole_fac: float = 1.0
    weight_fac: float = 1.0
    # 隧道爬速因子留白：无对应玩法，趴行恒 2.5 不分种族

    # 饱食：上限/冬眠阈（整数格）
    max_food: int = 5
    food_hibernate: int = 4

    jump_head: float = -4.0
    jump_feet: float = -3.0
    jump_boost: float = 8.0
    # 每跳一次的气喘增量（×1/9）
    jump_aerobic: float = 1.0

    flip_head: float = -9.0
    flip_feet: float = -7.0
    flip_boost: float = 5.0

    roll_rocket_vx_mult: float = 1.0

    # 后空翻 Belly→Flip；backflip_vx 用作 rd*(-backflip_vx)
    backflip_vx: float = 7.0
    backflip_c0_vy: float = -10.0
    backflip_c1_vy: float = -11.0

    # 滑铲火箭 Belly→Rocket；belly_rocket_vy 用作 -y
    belly_rocket_vx: float = 9.0
    belly_rocket_vy: float = 8.5

    # 超级扑跳冲量；普通扑跳 1.5 无差异，写死
    pounce_super: float = 9.0

    # 滑铲前冲正弦峰值；belly_no_kick=省略起始后蹬（仅溪流）
    belly_slide_spd: float = 18.1
    # 累倒时的滑铲正弦峰值
    belly_slide_spd_tired: float = 18.1
    belly_no_kick: bool = False

    # 计时<此值按跳键=取消滑铲
    belly_jump_cancel_window: int = 12
    # 同向跑 tick 数>此值才可起刹
    skid_init_thresh: int = 10
    # 被顶时跳起让路：持跳 tick、横向让开速度
    makeway_hop_hold: int = 8
    makeway_evade_vx: float = 2.8

    # 竖杆跳 beam jump：无持跳续力，y↓取负
    pole_jump_head_vx: float = 6.0
    pole_jump_head_vy: float = -8.0
    pole_jump_feet_vx: float = 5.0
    pole_jump_feet_vy: float = -7.0

    buoyancy: float = 0.95
    lungs_fac: float = 1.0
    swim_boost_force: float = 3.0
    swim_boost_cost: float = 0.2
    swim_boost_cd: int = 20
    swim_surface_speed: float = 2.7
    drown_threshold: float = 1.0 / 3.0  # 缺氧挣扎/自救阈
    swim_force_fac: float = 1.0
    bubble_fac: float = 1.0
    swim_leap_fac: float = 1.0  # 水里错开时上跳的力度

    # 落地速度超过此值摔晕 / 摔死
    fall_stun_speed: float = 35.0
    fall_death_speed: float = 60.0

    # 身体、臀部贴图的横向粗细
    body_width: float = 1.0
    hip_width: float = 1.0
    # 头贴图横向缩放、两肩间距的倍数
    head_width: float = 1.0
    shoulder_width: float = 1.0
    # 睡着时也睁着眼，只偶尔眨一下
    sleep_eyes_open: bool = False

    # 0-based，HUD 显示 +1；None=用全局 KARMA_MAX
    karma_cap: int | None = None

    # 投矛力气 0/1/2：0 飞得近、伤害低，2 飞得远、伤害高
    throw_skill: int = 1
    # 矛只能抛出去，投不出投掷态
    spear_toss: bool = False
    # 大件（矛）也能两手各拿一件
    dual_wield: bool = False

    def __post_init__(self):
        object.__setattr__(self, "_h", hash(tuple(getattr(self, f.name) for f in fields(self))))

    def __hash__(self):
        return self._h


DEFAULT_STATS = SlugStats()
