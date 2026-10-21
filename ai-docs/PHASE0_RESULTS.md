# Phase 0 可行性验证结果

- 日期：2026-10-20
- 对应计划：`ai-docs/NATIVE_WAYLAND_PORT_PLAN.md` 的 Phase 0
- 结论：**Go（有条件）**。没有发现必须回退 XWayland 的阻塞项；进入 Phase 1 前必须落实输入区域提交、子控件本地坐标和窗口级 DPR 三项约束。
- 源码改动：**无**。验证脚本当时放在 `/tmp/opencode/`，现已归档到 `verification/scripts/`；仓库只新增文档和本地验收记录。

---

## 1. 环境

| 项 | 值 |
| --- | --- |
| 桌面 | KDE Plasma 6.8.0 / KWin 6.8.0 / Wayland |
| Qt | PySide6 6.12（项目 `uv` 环境） |
| 主屏 | `eDP-1`，1440×900，窗口 DPR 2.0 |
| 副屏 | `HDMI-A-1`，1707×1067；KWin 逻辑尺寸约 1707.333×1067.333；窗口 DPR 1.5 |
| 输入注入 | `/dev/uinput` 虚拟相对/绝对鼠标、虚拟键盘，仅用于测试，不是产品方案 |

> 当前 `QScreen.devicePixelRatio()` 对两块屏都报 2.0，但 HDMI 上实际窗口的 `devicePixelRatioF()` 是 1.5。**不能只用 `QScreen` 的 DPR 做坐标换算。**

---

## 2. 总表

| 验证项 | 结果 | 说明 |
| --- | --- | --- |
| KWin 设置窗口几何 | **通过** | overlay 被设置为 HDMI 全屏；应用侧尺寸 1707×1067 |
| KWin 置顶 / 跳过任务栏 | **通过** | `keepAbove = true`、`skipTaskbar = true` 生效 |
| KWin → DBus 光标 | **通过** | Python `QtDBus` 持续收到 `workspace.cursorPos` |
| 输入区域 / 穿透 | **通过，有关键条件** | `set_input_region` 后必须提交表面；否则区域不生效 |
| 子控件嵌入 | **通过，需 Phase 2 坐标改造** | `TabBar`/`ControlHud` 可 reparent；点击、动画、按键可用 |
| 键盘焦点 | **通过** | `QLineEdit` 收到 `a`；`ControlHud` 收到方向键 |
| KWin 全局热键 | **通过** | `loadScript` 模式下 `registerShortcut` 生效，Ctrl+Alt+P 回调成功 |
| 托盘 | **通过** | `QSystemTrayIcon` 注册 StatusNotifierItem，`Activate` 触发；菜单动作可执行 |
| DPR / 坐标 | **通过** | 1.5 和 2.0 下点击换算误差均为 0 px |

---

## 3. 详细结果

### 3.1 KWin 几何、置顶、跳过任务栏

测试窗标题 `phase0-overlay`，KWin 脚本：

```js
var s = workspace.screens[1];              // HDMI-A-1
var g = Object.assign({}, s.geometry);     // 必须中转，不能直接赋 Rect
w.frameGeometry = g;
w.keepAbove = true;
w.skipTaskbar = true;
```

KWin 日志：

```text
phase0 overlay placed KWin::RectF(0, 900, 1707.3333333333333, 1067.3333333333333) keepAbove true
```

应用侧：

```text
OVERLAY_GEO QRect(0, 0, 1707, 1067)
TARGET_GEO  QRect(0, 900, 900, 700)
SCREEN      QRect(0, 0, 1440, 900)
```

结论：

- `frameGeometry` 的尺寸设置生效，应用侧从 1440×900 变成 1707×1067。
- Wayland 客户端仍然不知道自己的全局位置；`QWidget.geometry()` 仍是 `(0,0)`，全局位置只能来自 KWin。
- 1707.333 被应用侧取整为 1707，误差 0.333 px，满足 ≤1 px。
- `keepAbove`、`skipTaskbar` 均生效；`skipTaskbar` 的窗口不会出现在 KWin 窗口快照中。

### 3.2 KWin → DBus 光标

Python 服务使用 PySide6 的 `ClassInfo` 固定 D-Bus 接口：

```python
@ClassInfo({"D-Bus Interface": "org.slugcatpet.Phase0"})
class Service(QObject):
    @Slot(int, int)
    def Cursor(self, x, y): ...
```

KWin：

```js
callDBus("org.slugcatpet.Phase0", "/Phase0",
         "org.slugcatpet.Phase0", "Cursor",
         workspace.cursorPos.x, workspace.cursorPos.y);
```

收到：

```text
CURSOR 477 1282
CURSOR 0 900
CURSOR 284 1184
```

结论：DBus 桥可行。正式实现仍需处理：

- 服务名/接口名固定；
- Python 服务在 app 退出时注销；
- KWin 脚本加载失败时的状态上报；
- 光标更新节流，避免每个鼠标事件都走 DBus。

### 3.3 输入区域与点击穿透（★ 关键发现）

#### 协议层

`QWindow.setMask(QRegion(0, 0, 300, 300))` 后，`WAYLAND_DEBUG` 可见：

```text
wl_compositor#4.create_region(new id wl_region#60)
wl_region#60.add(0, 0, 300, 300)
wl_surface#51.set_input_region(wl_region#60)
wl_surface#51.commit()
```

#### 关键条件：setMask 后必须提交表面

第一次测试只调用了：

```python
self.windowHandle().setMask(r)
```

协议里出现了 `set_input_region`，但之后**没有 `wl_surface.commit()`**。结果输入区域没有生效：在 overlay 的 300×300 区域之外点击，仍然被 overlay 接收。

日志：

```text
OVERLAY_MASK PySide6.QtCore.QRect(0, 0, 300, 300)
OVERLAY_CLICK 1401 1001      # 本应在区域外穿透，却仍落到 overlay
```

修正为：

```python
self.windowHandle().setMask(r)
self.windowHandle().requestUpdate()  # 触发提交
self.update()
```

之后协议中出现：

```text
wl_surface#51.set_input_region(wl_region#60)
...
wl_surface#51.commit()
```

再点击：

```text
TARGET_CLICK 477 354         # 全局 (477,1282)，目标窗局部 (477,354)
OVERLAY_CLICK 284 284        # 全局 (284,1184)，overlay 局部 (284,284)
```

结论：**输入区域更新必须和一次表面提交绑定**。正式实现应在 `set_input_region()` 后统一调用 `window.requestUpdate()`，并在窗口尺寸/输出变化后重新计算并提交。

#### 全穿透

无交互区域时使用表面外 1×1：

```python
QRegion(self.width(), self.height(), 1, 1)
```

日志：

```text
OVERLAY_OUTSIDE QRect(1707, 1067, 1, 1)
TARGET_CLICK 477 354
```

结论：全穿透可用。不要使用空 `QRegion`；空区域在 Qt Wayland 下会发送 `set_input_region(nil)`，等价于整窗接收输入。

#### 坐标

- overlay 无边框，KWin 全局原点 `(0,900)`；
- 点击全局 `(284,1184)` → overlay 局部 `(284,284)`；
- 点击全局 `(477,1282)` → 目标窗局部 `(477,354)`；
- 误差 0 px；
- `QWindow.setMask` 使用逻辑局部坐标，不乘 DPR。

### 3.4 子控件嵌入

#### 通用子控件

overlay 内放 `QLineEdit`，点击后键盘输入 `a`：

```text
EDIT_TEXT 'a'
```

说明 overlay 子控件能正常绘制、接收键盘输入。

#### 真实 `TabBar`

把真实 `TabBar` 构造后 reparent 到 overlay：

```python
tab = TabBar(fake_pet, app, {})
tab.setParent(overlay)
tab.setWindowFlags(Qt.Widget)
tab.show()
```

- 收起态位于 overlay 本地 `(600,100,24,48)`；
- 用虚拟鼠标点击右侧箭头，`TabBar` 执行 `toggle()`；
- 日志：

```text
REPORT TAB QRect(-112, 0, 136, 177) EXPANDED True ... FOCUS QPushButton
```

这次测试桩把 `tab._screen` 设成了箭头自身矩形，所以展开态坐标错误地变成负值；这不是协议/架构失败。把 `_screen` 设为 overlay 本地矩形后，离线布局验证为：

```text
COLLAPSED QRect(600, 100, 24, 48) False
EXPANDED  QRect(1571, 100, 136, 177) True
panel     QRect(16, 0, 120, 177)
```

结论：真实 `TabBar` 可作为子控件绘制、点击、执行 150 ms 展开动画。Phase 2 必须把以下字段/方法从“屏幕全局坐标”改成“overlay 本地坐标”：

- `_screen` → `overlay.rect()`；
- `_edge_x`、`_y`、`_apply_collapsed()`、`_apply_expanded()`；
- `_animate_to()` 的几何；
- 箭头拖动 `eventFilter()`；
- `_toast()` 的定位；
- `install_tip`/tooltip 的 popup 位置。

#### 真实 `ControlHud`

真实 `ControlHud` reparent 后成功创建；Wayland 键盘事件到达子控件：

```text
CTRL_KEY 16777236            # Qt.Key_Right
```

离线按键映射验证：

```text
AFTER_D 1 0 [68]             # D 键 → x=+1
AFTER_RELEASE 0 []
```

说明 `ControlHud` 的按键收包、`_held`、`current_input()` 逻辑可复用。

注意：测试中点击落点偏到 overlay，而不是 `ControlHud` 本身；真实桌面上的点击/拖动还没有完全复验。Phase 2 必须把：

- `_place()` 改为 overlay 本地定位；
- `mousePressEvent()` / `mouseMoveEvent()` 的 `globalPosition() - frameGeometry().topLeft()` 改为 overlay 局部拖拽；
- `showEvent()` 中的 `activateWindow()` 改为“激活 overlay 表面 + `setFocus()`”；
- `_set_paused()` 的重心重排改为本地坐标。

### 3.5 键盘焦点

- `QLineEdit` 在 overlay 内收到 `a`，说明 Wayland 键盘焦点能进入 overlay 子控件；
- `ControlHud` 收到 `Qt.Key_Right`，说明真实控制面板的焦点路径可用；
- 失焦暂停逻辑本身未被破坏，但嵌入后需要区分“overlay 失焦”和“面板子控件失焦”，否则会在窗口内部切换时误暂停。

### 3.6 KWin 全局热键

KWin 脚本在 `loadScript` 模式下注册：

```js
registerShortcut("SlugcatPet Phase0 Test",
                 "Phase0 test shortcut",
                 "Ctrl+Alt+P",
                 function() {
                     callDBus("org.slugcatpet.Phase0", "/Phase0",
                              "org.slugcatpet.Phase0", "Hotkey", 5);
                 });
```

虚拟键盘发送 Ctrl+Alt+P：

```text
HOTKEY 5
```

KWin 日志：

```text
phase0 hotkey script loaded
phase0 hotkey fired
```

结论：不安装 KWin 包、直接 `loadScript` 也能注册全局热键。冲突提示、注销、重复注册尚未测试，Phase 4 需要补。

### 3.7 托盘

`QSystemTrayIcon` 在 KDE 下：

```text
TRAY_SHOW True SUPPORTS True
```

`org.kde.StatusNotifierWatcher.RegisteredStatusNotifierItems` 出现 `:1.376/StatusNotifierItem`。调用：

```bash
qdbus6 :1.376 /StatusNotifierItem org.kde.StatusNotifierItem.Activate 0 0
```

应用收到：

```text
TRAY_ACTIVATED ActivationReason.Trigger
ACTION settings
```

结论：托盘注册、点击回调、QAction 菜单项均可用。正式应用只需把 `Settings`/`Music`/`Quit` 接到现有回调；这是 Phase 4 的接线工作。

### 3.8 DPR / 坐标

| 场景 | 窗口 `devicePixelRatioF()` | `QScreen.devicePixelRatio()` | 结果 |
| --- | --- | --- | --- |
| HDMI-A-1 上的 overlay | 1.5 | 2.0 | KWin 逻辑坐标与 Qt 局部坐标 1:1；点击误差 0 px |
| eDP-1 上的 overlay | 2.0 | 2.0 | 目标窗局部 `(1000,472)`、overlay 局部 `(100,100)`；误差 0 px |

关键结论：

- **不要用 `QScreen.devicePixelRatio()` 统一换算**；HDMI 上它会报 2.0，而窗口实际是 1.5。
- 用 `overlay.devicePixelRatioF()` 处理渲染缩放；
- 用 KWin 的**逻辑几何**处理全局窗口矩形和光标；
- 输入区域始终用 overlay 逻辑局部坐标。
- KWin 输出是 1707.333×1067.333，Qt 窗口是 1707×1067；边界换算需要 floor/round，允许 ≤1 px 误差。

2.0 下的真实点击已经用绝对坐标虚拟指针补测通过：

- 虚拟桌面 1707×1967 映射到 `ABS_X/ABS_Y` 的 0..32767；
- 点击全局 `(1000,500)`，目标窗收到局部 `(1000,472)`；
- 点击全局 `(100,100)`，overlay 收到局部 `(100,100)`；
- 两者误差均为 0 px。

同时发现一个必须处理的输出绑定问题：

- 如果应用最初创建在 HDMI 上，KWin 只用 `frameGeometry` 把它移到 eDP，Qt 窗口 DPR 仍然是 **1.5**；
- 在 `show()` 前显式 `setScreen(eDP)`，窗口 DPR 才变成 **2.0**；
- 因此正式实现不能只依赖 KWin 改 `frameGeometry`。启动时应先选目标 `QScreen` 并调用 `QWindow.setScreen()`，再把几何交给 KWin；运行中切换输出时，要更新/重建表面并复验 DPR。

相对虚拟指针会被限制在 HDMI 顶边，无法跨到 eDP；上面的 2.0 测试改用绝对指针设备完成。该输入注入方式仅用于验证，不是产品功能。

### 3.9 KWin 窗口快照

KWin 脚本构造 JSON 并通过 `callDBus` 发送：

```json
[
  {
    "caption": "ai-docs — Dolphin",
    "resourceClass": "org.kde.dolphin",
    "x": 119, "y": 125, "w": 1202, "h": 650,
    "full": false, "minimized": false
  }
]
```

结论：窗口列表、矩形、`fullScreen`、`minimized` 都可通过 KWin 脚本推给 Python；Phase 3 的 `envwatch`、`shelters` 和“挡雨窗口”有数据来源。

---

## 4. 必须落实到实现的结论

1. **输入区域提交**
   - `setMask()` 后必须 `requestUpdate()`；
   - 窗口尺寸/输出变化后重新计算并提交；
   - 无交互时用表面外 1×1，不用空 `QRegion`。

2. **子控件本地坐标**
   - `TabBar`/`ControlHud`/`RainDial`/`RainCard` 的 `_screen`、`_edge_x`、`_y`、`_place()`、拖拽、toast、popup 全部改为 overlay 本地坐标；
   - 禁止再调用顶层 `move()`/`setWindowFlags()` 作为定位手段。

3. **DPR 与输出绑定**
   - 使用 `window.devicePixelRatioF()`，不能用 `QScreen.devicePixelRatio()` 统一乘；
   - 全局坐标来自 KWin；
   - 输入区域用逻辑坐标；
   - `show()` 前显式 `setScreen(target_screen)`；不能只依赖 KWin 改 `frameGeometry`，否则窗口 DPR 可能停留在旧屏；
   - 运行中切换输出时更新/重建表面并复验 DPR。

4. **焦点**
   - 点击 overlay 后激活 overlay 表面；
   - 子控件用 `setFocus()`；
   - 区分 overlay 失焦与内部焦点切换，避免 ControlHud 误暂停。

5. **KWin 脚本生命周期**
   - app 退出时卸载脚本/注销热键；
   - 脚本加载失败要显示在设置/托盘状态中；
   - 热键冲突要有日志和降级提示。

---

## 5. Go / No-Go

**Go。**

没有发现需要停止原生路线、回退 XWayland 的阻塞项。所有关键能力都已在 KWin 6.8 上跑通：

- KWin 能定位/置顶/跳过任务栏；
- DBus 光标桥可用；
- 输入区域和全穿透可用（前提是提交表面）；
- 子控件可嵌入并接收点击/键盘；
- `loadScript` 模式全局热键可用；
- 托盘可用；
- 窗口快照可用；
- 1.5 和 2.0 DPR 下的点击换算均为 0 px 误差；2.0 需要显式绑定目标输出。

进入 Phase 1 的条件：

1. 先实现输入区域辅助并强制提交；
2. 先做 overlay 本地坐标系，再迁移面板；
3. 启动时显式绑定目标 `QScreen`，并验证跨输出切换时 DPR 不漂移；
4. ControlHud 焦点/暂停逻辑在嵌入后复验。

---

## 6. 测试脚本（已归档到 `verification/scripts/`）

以下文件已从 `/tmp/opencode/` 归档到 `verification/scripts/`，仅用于复现 Phase 0：

- `uinput_mouse.py`、`uinput_keyboard.py`：虚拟输入设备；
- `phase0_click_app.py`、`phase0_click.js`：输入区域/穿透/光标/热键；
- `phase0_edp_app.py`、`phase0_edp.js`：eDP 2.0 下的绝对指针点击；
- `phase0_panels_app.py`、`phase0_panels.js`：真实 TabBar/ControlHud 嵌入；
- `tray_actions_probe.py`：托盘注册/激活/菜单动作；
- `dpr_probe.py`、`dpr_probe.js`：1.5/2.0 DPR；
- `kwin_windowlist.js`、`meta_service.py`：窗口快照；
- `tabbar_layout_probe.py`、`controlhud_key_probe.py`：离线布局/按键。

复现时注意：

- 测试会移动真实鼠标指针，并短暂创建全屏 overlay；
- 测试脚本必须使用唯一窗口标题，并在结束后卸载 KWin 脚本；
- 不要在未设置输入区域的情况下运行真实 `PetWindow`，否则可能挡住桌面输入。
