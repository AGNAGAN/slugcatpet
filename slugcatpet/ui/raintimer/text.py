"""雨循环的读数文案：时长、倒计时、钟点，以及输入框里分钟数与钟点的解析。"""

from __future__ import annotations
import datetime as _dt
import re
import time

from ...i18n import t
from ...world.raintimer import DRY, DRY_MAX, IDLE


def fmt_span(seconds) -> str:
    """时长按分钟说：25 分钟、1 小时 30 分钟。"""
    m = max(1, round(seconds / 60))
    h, m = divmod(m, 60)
    if not h:
        return t("rt_min", m=m)
    return t("rt_hour", h=h) if not m else t("rt_hour_min", h=h, m=m)


def fmt_clock(seconds) -> str:
    """倒计时读数：12:30、1:02:03。"""
    s = max(0, int(seconds + 0.999))
    h, rest = divmod(s, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_at(ts) -> str:
    return time.strftime("%H:%M", time.localtime(ts))


def parse_input(text, now=None):
    """「40」→ ("span", 秒)，「14:30」→ ("at", 时间戳)，认不出为 None。"""
    s = text.strip().replace("：", ":")
    now = time.time() if now is None else now
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if h > 23 or mi > 59:
            return None
        at = _dt.datetime.fromtimestamp(now).replace(hour=h, minute=mi, second=0, microsecond=0)
        if at.timestamp() <= now:
            at += _dt.timedelta(days=1)
        return "at", at.timestamp()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        sec = float(s) * 60
        if 60 <= sec <= DRY_MAX:
            return "span", sec
    return None


def status_line(timer) -> str:
    """当前时段的一句读数，空闲时说单击开始多久。"""
    if timer.phase == IDLE:
        return t("rt_start", t=fmt_span(timer.dry_s))
    left = timer.remaining()
    if timer.phase == DRY:
        return t("rt_head_dry", left=fmt_clock(left), at=fmt_at(timer.end_ts))
    if left is None:
        return t("rt_head_forever", el=fmt_clock(timer.elapsed()))
    return t("rt_head_rain", left=fmt_clock(left))
