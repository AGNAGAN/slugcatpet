"""姿态过渡与趴行掉头状态机（控制路径专用，y↓），cy==+1 脚踩地。"""
from __future__ import annotations


def toggle_standing(body, inp0, inp1) -> None:
    """上键升沿→standing=true(StandUp 意图)；下键升沿→standing=false(DownOnFours 意图)。"""
    if inp0.y == 1 and inp1.y != 1:
        # 坡度/头顶实心检查：pet 无坡/砖 → 恒真
        body.standing = True
    elif inp0.y == -1 and inp1.y != -1:
        body.standing = False


def update_counters(body) -> None:
    c0, c1 = body.chunk0, body.chunk1
    body._ctrl_lower_on_ground = (getattr(body, "_ctrl_lower_on_ground", 0) + 1) if c1.on_floor else 0
    body._ctrl_upper_off_ground = 0 if c0.on_floor else (getattr(body, "_ctrl_upper_off_ground", 0) + 1)


def anim_forces(body, move_x: int) -> None:
    c0, c1 = body.chunk0, body.chunk1
    flip = body.facing
    anim = body.animation

    if anim == "CrawlTurn":
        body.bodyMode = "Default"
        c0.vx += flip
        c1.vx -= 2.0 * flip
        if (move_x > 0) != (c0.x < c1.x):
            c0.vy += 3.0
            if c0.y > c1.y - 2.0:
                body.animation = None
                c0.vy += 1.0
        else:
            c0.vy -= 2.0
        if move_x == 0:                             # pet 无砖，跳过实心检查
            body.animation = None

    elif anim == "StandUp":
        if body.standing:
            c0.vx *= 0.7
            body.bodyMode = "Stand"                 # pet 恒真，略去检查
            if c0.y < c1.y - 3.0:
                body.animation = None
        else:
            body.animation = "DownOnFours"

    elif anim == "DownOnFours":
        if not body.standing:
            c0.vy += 2.0
            c0.vx += flip
            c1.vx -= flip
            if c0.y > c1.y or c0.on_floor:
                body.animation = None
        else:
            body.animation = "StandUp"


def crawl_turn_delay(body) -> None:
    body._ctrl_crawl_turn_delay = (getattr(body, "_ctrl_crawl_turn_delay", 0) + 1) if body.bodyMode == "Crawl" else 0


def posture_entry(body, move_x: int) -> None:
    if body.animation is not None:
        return
    c0, c1 = body.chunk0, body.chunk1
    mode = body.bodyMode
    if mode == "Crawl":
        if body.standing and getattr(body, "_ctrl_lower_on_ground", 0) >= 3:
            body.animation = "StandUp"
        elif ((move_x > 0) == (c0.x < c1.x)) and move_x != 0 and getattr(body, "_ctrl_crawl_turn_delay", 0) > 5:
            body._ctrl_crawl_turn_delay = 0
            body.animation = "CrawlTurn"            # pet 无砖，略去判定
    elif mode == "Stand":
        if (not body.standing
                and getattr(body, "_ctrl_lower_on_ground", 0) >= 5
                and getattr(body, "_ctrl_upper_off_ground", 0) >= 5):
            body.animation = "DownOnFours"
