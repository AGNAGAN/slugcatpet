"""雨计时器：按真实时间走的晴、雨两段；雨停算完成一次，业力升一档，循环时接着下一轮。"""

from __future__ import annotations
import time

IDLE, DRY, RAIN = "idle", "dry", "rain"

DRY_DEFAULT = 25 * 60
RAIN_DEFAULT = 5 * 60
DRY_MIN, DRY_MAX = 60, 12 * 3600
RAIN_MIN, RAIN_MAX = 60, 3600
EXTEND_S = 5 * 60  # 「再晚 / 再下 5 分钟」
SLACK_S = 15  # 轮询晚于时段结束这么久（关机、睡眠）就当中断
HALF_MIN_S = 5 * 60  # 晴天短于这个不弹半程
MUSIC_MIN_S = 3 * 60  # 雨短于这个不换场景曲
PIP_MIN, PIP_MAX = 4, 30
KARMA_TOP = 9  # 业力档 0~9


def pip_count(seconds) -> int:
    """一段时长的 pip 数：每分钟一个，限 4~30。"""
    return max(PIP_MIN, min(PIP_MAX, round(seconds / 60)))


class RainTimer:
    """cfg 是存档里的 rain_timer 字典，设置与进行中的时段都记在里面。"""

    def __init__(self, cfg: dict, clock=time.time):
        self._cfg = cfg
        self._clock = clock
        self.phase = IDLE
        self.start_ts = 0.0
        self.end_ts: float | None = None
        self.done = 0  # 本次启动完成的次数
        self.listeners = []  # fn(event)：start / half / last / rain / clear / stop / lost / extend
        self._half_sent = self._last_sent = False
        self._restore()

    # 设置

    @property
    def dry_s(self) -> int:
        return int(self._cfg.get("dry_s", DRY_DEFAULT))

    @dry_s.setter
    def dry_s(self, v):
        self._cfg["dry_s"] = int(max(DRY_MIN, min(DRY_MAX, v)))

    @property
    def rain_s(self) -> int:
        """0 表示一直下，直到手动停。"""
        return int(self._cfg.get("rain_s", RAIN_DEFAULT))

    @rain_s.setter
    def rain_s(self, v):
        self._cfg["rain_s"] = int(max(RAIN_MIN, min(RAIN_MAX, v))) if v else 0

    @property
    def loop(self) -> bool:
        return bool(self._cfg.get("loop", False))

    @loop.setter
    def loop(self, on):
        self._cfg["loop"] = bool(on)

    @property
    def karma(self) -> int:
        return min(self.done, KARMA_TOP)

    # 读数

    def now(self) -> float:
        return self._clock()

    def duration(self) -> float | None:
        if self.end_ts is None:
            return None
        return self.end_ts - self.start_ts

    def elapsed(self) -> float:
        return max(0.0, self.now() - self.start_ts) if self.phase != IDLE else 0.0

    def remaining(self) -> float | None:
        if self.phase == IDLE or self.end_ts is None:
            return None
        return max(0.0, self.end_ts - self.now())

    def progress(self) -> float:
        """当前时段走过的比例 0~1；一直下的雨为 0。"""
        d = self.duration()
        if self.phase == IDLE or not d:
            return 0.0
        return max(0.0, min(1.0, self.elapsed() / d))

    def pips(self) -> int:
        """当前该显示的 pip 数：空闲按下一轮晴天，进行中按本段。"""
        if self.phase == IDLE:
            return pip_count(self.dry_s)
        d = self.duration()
        return pip_count(d if d else self.rain_s or RAIN_DEFAULT)

    def rain_level(self):
        """这一刻该下的雨：最后一个 pip 时 drizzle，雨天 storm，其余 None。"""
        if self.phase == RAIN:
            return "storm"
        return "drizzle" if self.in_last_pip() else None

    def music_worthy(self) -> bool:
        """这场雨长到值得换场景曲：毛毛雨和短雨不换。"""
        if self.phase != RAIN:
            return False
        d = self.duration()
        return d is None or d >= MUSIC_MIN_S

    def in_last_pip(self) -> bool:
        if self.phase != DRY:
            return False
        n = self.pips()
        return self.progress() >= 1.0 - 1.0 / n

    # 操作

    def start(self, dry_s=None, remember=True):
        """开始晴天；remember 时把这次时长记作下次的默认。"""
        if dry_s is not None and remember:
            self.dry_s = dry_s
        span = self.dry_s if dry_s is None else max(DRY_MIN, min(DRY_MAX, dry_s))
        self._begin(DRY, self.now(), span)
        self._emit("start")

    def start_until(self, ts):
        """到某个时刻下雨，不改默认时长。"""
        self.start(max(DRY_MIN, ts - self.now()), remember=False)

    def rain_now(self):
        if self.phase == DRY:
            self._begin_rain(self.now())

    def stop_rain(self):
        """手动停雨，算完成。"""
        if self.phase == RAIN:
            self._complete(self.now())

    def cancel(self):
        if self.phase != IDLE:
            self._to_idle()
            self._emit("stop")

    def extend(self, seconds=EXTEND_S):
        if self.phase != IDLE and self.end_ts is not None:
            self.end_ts += seconds
            if self.phase == DRY:
                self._half_sent = self._half_sent and self.progress() >= 0.5
                self._last_sent = self._last_sent and self.in_last_pip()
            self._save()
            self._emit("extend")

    def poll(self):
        """按当前时间推进时段，发出跨过的事件。"""
        if self.phase == IDLE or self.end_ts is None:
            return
        now = self.now()
        if now >= self.end_ts:
            if now - self.end_ts > SLACK_S:
                self._to_idle()
                self._emit("lost")
            elif self.phase == DRY:
                self._begin_rain(self.end_ts)
            else:
                self._complete(self.end_ts)
            return
        if self.phase == DRY:
            if not self._half_sent and self.duration() >= HALF_MIN_S and self.progress() >= 0.5:
                self._half_sent = True
                self._emit("half")
            if not self._last_sent and self.in_last_pip():
                self._last_sent = True
                self._emit("last")

    # 内部

    def _begin(self, phase, at, span):
        self.phase = phase
        self.start_ts = at
        self.end_ts = None if span is None else at + span
        self._half_sent = self._last_sent = False
        self._save()

    def _begin_rain(self, at):
        self._begin(RAIN, at, self.rain_s or None)
        self._emit("rain")

    def _complete(self, at):
        self.done += 1
        if self.loop:
            self._begin(DRY, at, self.dry_s)
        else:
            self._to_idle()
        self._emit("clear")

    def _to_idle(self):
        self.phase = IDLE
        self.start_ts = 0.0
        self.end_ts = None
        self._save()

    def _save(self):
        if self.phase == IDLE:
            self._cfg.pop("run", None)
        else:
            self._cfg["run"] = {"phase": self.phase, "start": self.start_ts, "end": self.end_ts}

    def _restore(self):
        run = self._cfg.get("run")
        if not isinstance(run, dict) or run.get("phase") not in (DRY, RAIN):
            self._cfg.pop("run", None)
            return
        try:
            self.phase = run["phase"]
            self.start_ts = float(run["start"])
            self.end_ts = None if run.get("end") is None else float(run["end"])
        except (KeyError, TypeError, ValueError):
            self._to_idle()
            return
        if self.end_ts is not None and self.now() - self.end_ts > SLACK_S:
            self._to_idle()
            return
        self._half_sent = self.progress() >= 0.5
        self._last_sent = self.in_last_pip()

    def _emit(self, ev):
        for fn in list(self.listeners):
            fn(ev)
