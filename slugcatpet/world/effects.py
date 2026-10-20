"""窗口上的火花、冲击波等特效，以及劫持光标。"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QPainter


class EffectsMixin:
    def add_spark(self, x, y, vx, vy, white=True, life=80):
        self.sparks.append([x, y, vx, vy, float(life), float(life), white])

    def add_shockwave(self, x, y, maxr, flash=False):
        life = 8.0 if flash else 12.0
        self.shockwaves.append([x, y, 0.0, float(maxr), life, life, flash])

    def _cursor_to_device(self, logical_x, logical_y):
        dpr = self.devicePixelRatioF()
        return (
            (self._area.x() + logical_x * self._scale) * dpr,
            (self._area.y() + logical_y * self._scale) * dpr,
        )

    def _wayland_cursor_writer(self, dpr, target=None, global_origin=None):
        """把内部物理坐标换回目标表面坐标，再交给 QCursor。

        Qt 6.12 的 Wayland 插件用 ``wp_pointer_warp_v1`` 实现 ``QCursor.setPos``，
        但它把传入点当成「全局坐标」，再减去当前指针焦点窗口的
        ``windowFrameGeometry().topLeft()``。普通 xdg_toplevel 在 Wayland 上
        拿不到合成器给的全局位置；临时捕获面的 Qt 几何原点却可能是输出原点。
        因此先换成目标表面本地坐标，再补上 Qt 自己的 frame 原点，避免目标点
        被判定在窗口外。
        """
        from PySide6.QtGui import QCursor

        scale = float(dpr) or 1.0
        surface = target if target is not None else self
        origin = global_origin if global_origin is not None else self._area.topLeft()
        width = max(1, int(surface.width()))
        height = max(1, int(surface.height()))

        def move(x, y):
            local_x = float(x) / scale - origin.x()
            local_y = float(y) / scale - origin.y()
            local_x = min(max(local_x, 0.0), width - 1.0)
            local_y = min(max(local_y, 0.0), height - 1.0)
            handle = surface.windowHandle()
            frame = handle.frameGeometry() if handle is not None else surface.frameGeometry()
            frame_origin = frame.topLeft()
            QCursor.setPos(
                QPoint(
                    round(local_x + frame_origin.x()),
                    round(local_y + frame_origin.y()),
                )
            )

        return move

    def _wayland_busy_cursor(self, on):
        """用应用级 override cursor 显示忙碌样式；只影响本应用表面。"""
        on = bool(on)
        if on == bool(getattr(self, "_wayland_busy", False)):
            return on
        from PySide6.QtWidgets import QApplication

        try:
            if on:
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            else:
                QApplication.restoreOverrideCursor()
        except Exception:
            return False
        self._wayland_busy = on
        return on

    def _begin_cursor_capture(self, token):
        """显示临时全屏捕获面，取得 KWin 的指针焦点后启用指针写入。"""
        if not getattr(self, "_wayland", False):
            return {}
        self._cursor_capture_owner = token
        self._cursor_capture = True
        capture = None
        show_capture = getattr(self, "_show_cursor_capture", None)
        if callable(show_capture):
            try:
                capture = show_capture()
            except Exception:
                capture = None
        dpr = self.devicePixelRatioF()
        target = capture if capture is not None else self
        if capture is not None:
            get_rect = getattr(self, "overlay_rect", None)
            origin = get_rect().topLeft() if callable(get_rect) else self._area.topLeft()
        else:
            origin = self._area.topLeft()
        return {
            "clip": lambda x, y: False,
            "unclip": lambda: None,
            "setpos": self._wayland_cursor_writer(dpr, target, origin),
            "busy_cursor": lambda: self._wayland_busy_cursor(True),
            "restore_cursor": lambda: self._wayland_busy_cursor(False),
        }

    def _cursor_hijack_released(self, token):
        if getattr(self, "_cursor_capture_owner", None) is not token:
            return
        self._cursor_capture_owner = None
        self._cursor_capture = False
        hide_capture = getattr(self, "_hide_cursor_capture", None)
        if callable(hide_capture):
            try:
                hide_capture()
            except Exception:
                pass

    def start_cursor_hijack(self, logical_x, logical_y, lock_ticks=None, knock_v=(0.0, 0.0)):
        """劫持光标；设置里关了抢光标则返回 None。knock_v 为逻辑 px/tick 的弹开初速。"""
        if not self.cfg_cursor_hijack or not getattr(self, "cursor_hijack_available", True):
            return None
        if self.cursor_hijack is not None:
            self.stop_cursor_hijack()
        from ..platform.cursorfx import CursorHijack

        dpr = self.devicePixelRatioF()
        dev_x, dev_y = self._cursor_to_device(logical_x, logical_y)
        k = self._scale * dpr
        kw = {} if lock_ticks is None else {"lock_ticks": lock_ticks}
        token = object()
        callbacks = self._begin_cursor_capture(token)
        try:
            self.cursor_hijack = CursorHijack(
                dev_x,
                dev_y,
                self._area.width() * dpr,
                self._area.height() * dpr,
                self._area.x() * dpr,
                self._area.y() * dpr,
                replace_cursor=self.cfg_cursor_shape,
                knock_v=(knock_v[0] * k, knock_v[1] * k),
                on_release=lambda: self._cursor_hijack_released(token),
                **callbacks,
                **kw,
            )
        except Exception:
            self._cursor_hijack_released(token)
            raise
        return self.cursor_hijack

    def start_cursor_hold(self, logical_x, logical_y, max_ticks):
        if not self.cfg_cursor_hijack or not getattr(self, "cursor_hijack_available", True):
            return None
        if self.cursor_hijack is not None:
            self.stop_cursor_hijack()
        from ..platform.cursorfx import CursorHijack

        dpr = self.devicePixelRatioF()
        dev_x, dev_y = self._cursor_to_device(logical_x, logical_y)
        token = object()
        callbacks = self._begin_cursor_capture(token)
        try:
            self.cursor_hijack = CursorHijack(
                dev_x,
                dev_y,
                self._area.width() * dpr,
                self._area.height() * dpr,
                self._area.x() * dpr,
                self._area.y() * dpr,
                mode="hold",
                watchdog_max=max_ticks,
                replace_cursor=self.cfg_cursor_shape,
                on_release=lambda: self._cursor_hijack_released(token),
                **callbacks,
            )
        except Exception:
            self._cursor_hijack_released(token)
            raise
        return self.cursor_hijack

    def move_cursor_hold(self, logical_x, logical_y):
        hj = self.cursor_hijack
        if hj is not None and hj.mode == "hold" and hj.active:
            hj.hold_at(*self._cursor_to_device(logical_x, logical_y))

    def stop_cursor_hijack(self):
        if self.cursor_hijack is not None:
            self.cursor_hijack.release()
            self.cursor_hijack = None

    def _update_fx(self):
        alive = []
        for s in self.sparks:
            s[0] += s[2]
            s[1] += s[3]
            s[3] += 0.45
            s[2] *= 0.93
            s[3] *= 0.93
            s[4] -= 1.0
            if s[4] > 0:
                alive.append(s)
        self.sparks = alive

        sw = []
        for w in self.shockwaves:
            w[4] -= 1.0
            t = 1.0 - w[4] / w[5]
            w[2] = w[3] * (t**0.5)
            if w[4] > 0:
                sw.append(w)
        self.shockwaves = sw

        if self.fx:
            self.fx = [q for q in self.fx if q.update()]

        if self.bubbles:
            surf = self.water_surface
            if surf is None:
                self.bubbles = []
            else:
                self.bubbles = [b for b in self.bubbles if b.update(surf.level_at(b.x), self._bubble_rng)]

        if self.cursor_hijack is not None and not self.cursor_hijack.update():
            self.cursor_hijack = None

    def _draw_fx_under(self, p):
        if not self.fx:
            return
        from .explosionfx_draw import draw_fx_under

        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        draw_fx_under(p, self.fx)
        p.restore()

    def _draw_fx(self, p):
        pet_fx = [
            fx
            for fx in (pet.behavior.exclusive_fx() for pet in self.pets if pet.behavior is not None)
            if fx is not None
        ]
        if not (self.shockwaves or self.sparks or self.fx or pet_fx):
            return
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        from PySide6.QtGui import QPen

        for w in self.shockwaves:
            a = int(200 * (w[4] / w[5]))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, a), 1.4))
            p.drawEllipse(QPointF(w[0], w[1]), w[2], w[2])
        p.setPen(Qt.PenStyle.NoPen)
        for s in self.sparks:
            a = int(230 * (s[4] / s[5]))
            p.setBrush(QColor(255, 255, 240, a) if s[6] else QColor(*self.layout_data.tint, a))
            p.drawEllipse(QPointF(s[0], s[1]), 0.9, 0.9)
        if self.fx:
            from .explosionfx_draw import draw_fx_over

            draw_fx_over(p, self.fx)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        for fx in pet_fx:
            fx.draw(p)
        p.restore()
