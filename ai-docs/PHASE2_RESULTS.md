# Phase 2 结果：UI 嵌入主表面

- 日期：2026-10-20
- 对应计划：`ai-docs/NATIVE_WAYLAND_PORT_PLAN.md` 的 Phase 2
- 结论：**Phase 2 完成（第一版）**。除设置、音乐、首次启动外的浮动 UI 已进入 overlay；Wayland 下只保留一个全屏顶层表面，面板和卡片使用 overlay 局部逻辑坐标。
- 验证环境：KDE Plasma 6.8 / KWin 6.8 / Wayland，PySide6 6.12；eDP-1 1440×900，窗口 DPR 2.0。

---

## 1. 实现内容

### 1.1 overlay 子控件宿主

`slugcatpet/window.py` 增加：

- `is_overlay = True`：作为“当前顶层窗口是否需要局部坐标”的识别标记，避免设置/音乐窗口被误嵌入。
- `_overlay_cards`：登记 RainCard、确认框、珍珠编辑器等临时子控件。
- `register_overlay_widget()` / `unregister_overlay_widget()`：
  - 临时控件显隐时立即重算输入区域；
  - 控件销毁时自动从登记表移除。
- `_reflow_overlay_cards()`：overlay 尺寸变化后把临时控件重新夹回可见范围。
- `_modal_card_blocks()`：确认框等卡片打开时，卡片外的点击不再落到猫或物品上。
- `_build_input_region()`：存在可见 overlay 卡片时临时使用整窗输入区域，保证模态点击能被 overlay 接住；卡片关闭后立即恢复按需输入区域。
- `OverlayHost` 计划中的职责拆分到了更小的 `slugcatpet/ui/overlay.py` 工具函数和 `PetWindow` 的登记接口中，避免再引入一层难以调试的间接对象。

### 1.2 常驻面板

已全部改为 overlay 子控件，并保留 Windows 顶层路径：

| 组件 | 改动 |
| --- | --- |
| `TabBar` | `parent/embedded` 构造参数；位置、箭头拖动、toast 全部使用 overlay 本地坐标；动画每帧刷新输入区域 |
| `HudPanel` | `_place()` / `_move_to()` 使用本地坐标；整窗拖动改用 `ev.position()`；显隐和移动刷新输入区域 |
| `ControlHud` | 去掉嵌入式顶层 flags；`window().activateWindow()`；拖动改本地 delta；按 Esc 退出控制；失焦暂停逻辑保留 |
| `RainDial` | 表盘、拖动、状态提示全部本地化；提示 `_tip` 改为 overlay 子 `QLabel`；右键卡片锚点使用 `_center_local()` |
| TabBar toast | 嵌入时作为 overlay 子 label，不再使用 `Qt.ToolTip` 顶层 |

### 1.3 RainCard

`slugcatpet/ui/raintimer/card.py`：

- 嵌入模式不再是 `Qt.Popup`，而是 overlay 的直接子控件。
- 锚点使用 overlay 本地 `QRect`；按 `sides` 顺序选择放得下的一侧，并夹在 overlay 内。
- 点卡片外面关闭、Esc 关闭：
  - 通过应用级事件过滤器处理；
  - 卡片打开时 overlay 使用整窗输入区域；
  - 点外面的一下由卡片消费，不会继续点到底下的桌面或猫。
- 从托盘打开且没有可靠托盘几何时，固定锚在 overlay 右下角，向左上展开。
- 从 TabBar 按钮打开时，锚点由按钮 `mapTo(overlay, ...)` 得到，不再依赖全局坐标。

### 1.4 确认框与 overlay 内对话框

`slugcatpet/ui/widgets/dialogs.py`：

- `CardDialog` 新增 `embedded` 参数；当 parent 是 overlay 时自动嵌入，设置/音乐里的对话框保持普通 transient `QDialog`。
- 嵌入时：
  - 使用 `Qt.Widget`，成为 overlay 子控件；
  - 居中或拖动只写 overlay 局部坐标；
  - 打开时登记到 overlay，关闭时注销并刷新输入区域；
  - 应用级事件过滤器吞掉卡片外的点击，形成模态效果；
  - Esc、按钮和 `finished` 信号保持原行为。
- 因此猫的“杀死确认”、物品移除确认、珍珠编辑器和设置中的普通确认框共用同一套代码；前两者在 overlay 内，设置里的仍在设置窗内。

### 1.5 CatMenu 与工具提示

- `PetWindow.open_cat_menu(pet, pos, local=False)`：
  - Windows 仍使用 `menu.exec(globalPos)`；
  - Wayland 使用 `menu.popup(overlay.mapToGlobal(localPos))`，菜单 parent 是 overlay；
  - 菜单不再阻塞事件循环，关闭后自动释放。
- HUD 行右键、拖动都改为 overlay 本地坐标；HUD 行左键仍然打开猫菜单。
- `HoverTip` 在 overlay 内创建子 `QLabel`，用 `mapTo(overlay, ...)` 定位并夹在 overlay 内；设置/音乐里的工具提示仍使用原来的顶层提示。

### 1.6 坐标迁移

`slugcatpet/ui/overlay.py`：

- 首次 Wayland 启动时把旧存档里的 `hud_x/hud_y`、`tab_y`、`rain_timer.dial_pos` 从全局坐标换成 overlay 局部坐标。
- 同时兼容 Phase 1 已经保存成本地坐标的情况：先判断点是否落在 overlay 的全局矩形内，否则保留本地值。
- 迁移后写入 `params["ui_coord_space"] = "overlay"`，后续启动不再重复减原点。
- 明显越界的值由各面板自己的 clamp 回退到可见范围。

### 1.7 设置 / 音乐 / 首次启动

- `SettingsWindow`、`MusicPanel` 仍是普通 `xdg_toplevel`，没有新增自定义 `move()`。
- `SetupPanel` 从 `QWidget + StaysOnTop` 改为普通 `QDialog`，去掉了按屏幕坐标居中；位置交给合成器。
- 由于素材初始化发生在 `PetWindow` 创建之前，第一版没有可用的 overlay 作为 transient parent；这一点在下方“偏差与遗留”中说明。

### 1.8 Windows 行为

所有 Windows 顶层路径都保留在 `_embedded == False` / `not _wayland` 分支：

- HudPanel、TabBar、ControlHud、RainDial 仍使用 `Qt.Tool + StaysOnTop`；
- RainCard 仍使用 `Qt.Popup`；
- CatMenu 仍使用 `exec(globalPos)`；
- 工具提示仍使用顶层 `ToolTip`；
- 对话框仍使用原来的屏幕居中/拖动逻辑。

---

## 2. 验证

### 2.1 自动检查

- `uv run ruff check .`：通过
- `uv run ruff format --check .`：通过（281 个文件）
- `uv run python -m unittest discover -s tests -v`：15 个测试通过
- `uv run python tools/params_doc.py --check`：文档是最新的

新增 `tests/test_wayland_overlay.py`，覆盖：

- overlay 内卡片左上角 clamp；
- 下方输出（HDMI）旧全局坐标迁移；
- Phase 1 已保存成本地坐标时不重复减原点；
- `ui_coord_space` 标记的幂等性。

### 2.2 实际 KWin 会话

在 eDP-1 上通过 uinput 注入鼠标/键盘并截图验证：

- TabBar 在 overlay 右侧显示，按钮点击正常；
- 从 TabBar 打开雨循环卡片，卡片位于表盘/侧栏旁；
- 点卡片外关闭，点击被卡片消费，不会穿透到桌面；
- HUD 行左键打开 CatMenu，菜单在行旁弹出；
- 猫菜单打开“杀死该猫”确认框，确认框在 overlay 内居中显示，取消按钮正常；
- 启动控制模式后 ControlHud 在 overlay 底部显示，Esc 退出；
- HUD 工具提示作为 overlay 子 label 显示在面板下方；
- 退出应用后 KWin 脚本正常卸载。

临时截图和测试脚本在 `/tmp/opencode/phase2-*`，不属于仓库内容。

---

## 3. 偏差与遗留

1. **设置/音乐内的局部弹层没有迁到 overlay**  
   `appearance.py` 的皮肤选择/尾巴弹层和 `scenemusic.py` 的音量条属于 Settings/Music 自己的 transient popup，仍然使用 `Qt.Popup + mapToGlobal`。它们不在 overlay 坐标系里，迁到 overlay 反而会盖在设置窗之上。它们不是 `Qt.Tool` 顶层，不违反 Phase 2 退出标准；如果后续要求设置内部也完全局部化，可单独改成设置窗子控件。

2. **SetupPanel 没有 overlay transient parent**  
   首次素材初始化早于 `PetWindow`，当前没有可用的 overlay 父窗口。第一版只去掉自定义居中，交由 KWin 放置。等 Phase 5 打包时可以考虑先建一个轻量宿主窗口，或把素材初始化推到 overlay 出现之后。

3. **`place_center()` 名称保留**  
   嵌入卡片的 `CardDialog.place_center()` 仍存在，但嵌入分支只计算 overlay 局部坐标并调用子控件 `move()`；不再设置顶层窗口全局位置。Windows/设置路径保持原逻辑。

4. **overlay 首次显示抢焦点仍未解决**  
   这是 Phase 1 已记录的问题；Phase 2 没有改变 `PetWindow.show()` 的激活行为。控制模式需要 overlay 获得焦点，因此当前没有简单地在 show 时禁用激活。

5. **托盘雨卡片使用右下角降级锚点**  
   Wayland 没有可靠托盘图标几何；只有表盘可见时用表盘中心，否则固定 overlay 右下角。后续如有托盘协议/DBus 几何，可替换锚点。

6. **多输出完整交互仍属 Phase 3/后续**  
   本阶段重点验证 eDP-1；HDMI 的 overlay 原点迁移已有单元测试，但跨输出拖动、全屏检测和挡雨窗口仍按计划留给后续阶段。

7. **退出时偶发 QtWayland 竞态**  
   有两次用 SIGINT 退出时在 `QWaylandWindow::decoration` 段错误；随后普通模式、不同 shutdown 变体和 HEAD 基线多次回归均未稳定复现。现有 `PetWindow.shutdown()` 已停帧、丢弃排队重绘并隐藏表面，初步判断是 Qt 6.12 Wayland 退出竞态，不阻塞 Phase 2；升级 Qt 或再次稳定复现时再单独处理。

---

## 4. 主要文件

新增：

- `slugcatpet/ui/overlay.py`
- `tests/test_wayland_overlay.py`
- `ai-docs/PHASE2_RESULTS.md`

修改：

- `slugcatpet/window.py`
- `slugcatpet/main.py`
- `slugcatpet/petunit.py`
- `slugcatpet/ui/widgets/dialogs.py`
- `slugcatpet/ui/widgets/tips.py`
- `slugcatpet/ui/raintimer/card.py`
- `slugcatpet/ui/raintimer/dial.py`
- `slugcatpet/ui/panels/tabbar.py`
- `slugcatpet/ui/panels/hud.py`
- `slugcatpet/ui/panels/hudrow.py`
- `slugcatpet/ui/panels/controlhud.py`
- `slugcatpet/ui/panels/setup_panel.py`

---

## 5. 下一阶段

Phase 2 已完成。下一阶段进入 Phase 3：

- 扩展 KWin 脚本：活动窗口全屏状态、窗口矩形快照；
- `foreground_fullscreen()` / `window_rects()` 接回挡雨逻辑；
- 注册全局快捷键并处理冲突；
- 在 eDP/HDMI 两种输出上验证全屏收起、恢复和点击路由。
