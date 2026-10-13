"""自动帧率：在刷新率的整数分频档间按实测帧况升降。"""

MIN_RATE = 30.0
WINDOW_S = 1.0  # 统计窗口
SLOW_RATIO = 1.25  # 实测帧间隔超目标这么多算跟不上
BAD_WINDOWS = 2  # 连续这么多个窗口跟不上才降档
HEADROOM = 0.6  # 帧内耗时低于高一档间隔的这个比例才试升
PROBE_BASE_S = 10.0
PROBE_MAX_S = 160.0
PROBE_HOLD_S = 5.0  # 试升后撑过这么久算成功


def rate_tiers(hz):
    """hz, hz/2, hz/3 … 不低于 MIN_RATE（至少保留一档）。"""
    tiers = [hz]
    n = 2
    while hz / n >= MIN_RATE:
        tiers.append(hz / n)
        n += 1
    return tiers


class FramePacer:
    def __init__(self, hz=60.0):
        self.reset(hz)

    def reset(self, hz):
        self.hz = hz
        self._tiers = rate_tiers(hz)
        self._level = 0
        self._probe_s = PROBE_BASE_S
        self._probing = False
        self._since = 0.0  # 在当前档累计的活跃时长
        self._bad = 0
        self._clear()

    def _clear(self):
        self._sum_dt = 0.0
        self._sum_busy = 0.0
        self._n = 0

    @property
    def rate(self):
        return self._tiers[self._level]

    def frame(self, dt, busy, iv_s):
        """记一帧（实测间隔、帧内耗时、目标间隔，单位秒），档位变了返回 True。"""
        self._sum_dt += dt
        self._sum_busy += busy
        self._n += 1
        self._since += dt
        if self._sum_dt < WINDOW_S:
            return False
        avg_dt = self._sum_dt / self._n
        avg_busy = self._sum_busy / self._n
        self._clear()
        if avg_dt > iv_s * SLOW_RATIO:
            self._bad += 1
            if self._bad < BAD_WINDOWS or self._level >= len(self._tiers) - 1:
                return False
            if self._probing:
                self._probe_s = min(self._probe_s * 2.0, PROBE_MAX_S)
            self._shift(+1)
            return True
        self._bad = 0
        if self._probing and self._since >= PROBE_HOLD_S:
            self._probing = False
            self._probe_s = PROBE_BASE_S
        if self._level > 0 and self._since >= self._probe_s:
            if avg_busy < HEADROOM / self._tiers[self._level - 1]:
                self._shift(-1)
                self._probing = True
                return True
        return False

    def _shift(self, step):
        self._level += step
        self._since = 0.0
        self._bad = 0
        if step > 0:
            self._probing = False
