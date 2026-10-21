# 原生 Wayland 迁移剩余工作

- 日期：2026-10-20
- 依据：`PHASE0_RESULTS.md`、`PHASE1_RESULTS.md`、`PHASE2_RESULTS.md`、`PHASE3_RESULTS.md`、`PHASE4_RESULTS.md`、`PHASE5_CURSOR_WRITE.md`、`PHASE5_PACKAGING.md` 与当前代码审计
- 用途：记录 Phase 0–4 之后仍未完成的工作，作为 Phase 5 的执行清单
- 结论：**Phase 0–4 已完成；Phase 5 的 Wayland/KWin 光标写入、焦点保持、左/右键解除、Linux 打包、KWin 脚本持久安装/启用、desktop/图标、Linux CI 和 README 已完成。剩余最终验收（真实猫行为、Rain World 全屏、多输出逃逸、注销登录）和 Windows 完整行为回归。**

---

## 1. 状态总览

| 阶段 | 状态 | 说明 |
| --- | --- | --- |
| Phase 0 | 已完成 | 可行性闸门结论为 Go（有条件） |
| Phase 1 | 已完成 | 单主表面、输入区域、KWin 几何/置顶、光标桥 |
| Phase 2 | 已完成（第一版） | UI 嵌入 overlay、局部坐标、菜单/卡片/提示 |
| Phase 3 | 已完成 | 全屏、窗口快照、热键、冲突提示、设置页状态与重载；持久安装/启用在 Phase 5 完成 |
| Phase 4 | 已完成 | XDG 自启、输出选择、光标只读/写入能力、托盘锚点、transient 设置/音乐窗；desktop/图标在 Phase 5 完成 |
| Phase 5 | 接近完成 | 光标写入、焦点/点击、Linux 打包、KWin 持久安装、desktop/图标、CI、README 已完成；最终人工验收和 Windows 行为回归待做 |

---

## 2. Phase 3：KWin 桥剩余工作

### 2.1 已完成的基础

- KWin 脚本运行时加载/卸载。
- overlay 固定到目标几何。
- `keepAbove`、`skipTaskbar`、`skipSwitcher`。
- `workspace.cursorPosChanged` → DBus → Python 光标位置。
- DBus 服务与 `CursorMoved`、`OverlayGeometryChanged`、`Log`。
- 应用退出时正常卸载脚本。

相关文件：

- `slugcatpet/platform/wayland/kwin_bridge.py`
- `slugcatpet/platform/wayland/kwin_script/contents/code/main.js`
- `slugcatpet/platform/wayland/kwin_script/metadata.json`

### 2.2 已完成

- [x] 增加 DBus 信号/槽：
  - `FullscreenChanged`
  - `WindowListChanged`
  - `HotkeyPressed`
  - `HotkeyStatus`
- [x] 增加后端能力标志：
  - `supports_fullscreen`
  - `supports_shelters`
  - `supports_hotkeys`
- [x] 扩展 KWin 脚本：
  - 跟踪活动窗口和 `fullScreenChanged`
  - 生成窗口矩形 JSON 快照并推送
  - 过滤 overlay、dock/panel、tooltip、最小化窗口
  - 注册 `GLOBAL_KEYS` + `FROZEN_KEYS`
  - 输出/桌面变化时重新应用几何
- [x] 全屏检测接回 `EnvironmentWatcher`
  - 增加 `fullscreen_provider`
  - Wayland 下不再依赖 `SHQueryUserNotificationState` / `GetForegroundWindow`
  - 未更新时返回 `None`，保持原状态，不能误隐藏
- [x] 挡雨窗口接回 `PetWindow._poll_shelters()`
  - 新增 KWin 窗口快照提供者
  - 直接返回 overlay-local 逻辑矩形
  - 去掉 `self.x()/self.y()/dpr` 的全局换算
  - 桥不可用时返回空列表且不崩溃
- [x] 全局热键 Linux 路径
  - KWin `HotkeyPressed` 接到现有 `HotkeyFilter.triggered`
  - 用 KGlobalAccel `action(keyCode)` 检查快捷键最终归属
  - 冲突在日志和设置页给出可见提示
- [x] 设置页增加 KWin 状态与“重新加载 KWin 脚本”
- [x] 多输出实测
  - HDMI 全屏收起/恢复
  - eDP 全屏不误收起 HDMI overlay
  - 挡雨窗口跨输出过滤

详细记录见 `ai-docs/PHASE3_RESULTS.md`。

### 2.3 Phase 5 已完成

- [x] KWin 脚本安装/启用
  - 安装到 `$XDG_DATA_HOME/kwin/scripts/slugcatpet/`
  - 写 `$XDG_CONFIG_HOME/kwinrc` 的 `[Plugins] slugcatpetEnabled=true/false`
  - 调用 `org.kde.KWin.reconfigure`
  - 设置页增加「登录后自动加载 KWin 脚本」开关；默认关闭，必须由用户勾选
  - `metadata.json` 补上 `KPackageStructure: KWin/Script`
  - 运行时插件改名 `slugcatpet-runtime`，避免停用持久插件时被 KWin 连带卸载
- [x] 输出选择设置项（Phase 4）
- [ ] 用 Rain World 实际全屏窗口做一次最终验收（Phase 5）

### 2.4 Phase 3 退出标准

- [x] 全屏程序能按 `fullscreen_mode` 触发 hide/sink，退出全屏后恢复。
- [x] 挡雨窗口近似正确；KWin 快照不可用时雨不挡窗口且不崩溃。
- [x] 冻结/HUD/退出/步进热键可用，冲突有提示。
- [x] 关闭 KWin 脚本后明确降级，设置页能看到状态。
- [x] eDP 与 HDMI 至少各完成一次实际交互验证。

---

## 3. Phase 4：平台功能（已完成开发期）

- [x] XDG 开机自启
  - 写/删 `~/.config/autostart/org.slugcatpet.SlugcatPet.desktop`
  - 源码运行指向 `.venv/bin/python` + `run_slugcatpet.py`
  - `sync_path()` 启动时更新旧路径
- [x] 应用标识
  - 非 Windows 设置 `SlugcatPet` 应用名（不设置 `applicationDisplayName`，避免改 overlay 标题）
  - `setDesktopFileName()` 仅在 `.desktop` 已安装时启用
- [ ] 应用桌面文件与图标安装（转入 Phase 5 打包）
- [x] 输出选择
  - 持久化 `output` 参数
  - 设置页下拉框列出主屏/各输出
  - `EnvironmentWatcher` 跟随目标输出
- [x] 光标劫持/形状
  - Wayland 下通过临时全屏捕获面取得指针焦点，再用 Qt 6.12 `QCursor.setPos()` / `wp_pointer_warp_v1` 写入
  - 能移动、按住期间持续重定位、显示应用级忙碌样式
  - 左/右键单击解除劫持；捕获面吞掉解除点击，不传给下层窗口
  - KWin 脚本在捕获面和 overlay 首次映射后恢复原键盘焦点；ControlHud 在宽限期外的激活不受影响
  - Windows 用 `GetAsyncKeyState()` 轮询左/右键解除
  - 不支持写入时设置页灰显并说明“仍可跟随真实光标”
  - 详细记录见 `PHASE5_CURSOR_WRITE.md`；真实锁光标仍不可用
- [x] 托盘雨循环卡片锚点
  - 标签栏 → KWin 光标 → 表盘 → overlay 右下角
- [x] 置顶与从属窗口收尾
  - 设置/音乐保留顶层，使用 overlay transient parent
- [x] 帧同步
  - 第一版继续使用定时器降级

### Phase 4 退出标准

- [x] 自启开关可写/删 `.desktop`；文件内容和路径已测试，注销后实际拉起留 Phase 5 最终验收。
- [x] 全屏程序能隐藏/沉底，退出后恢复（Phase 3 已验收）。
- [x] 挡雨窗口近似正确（Phase 3 已验收）。
- [x] 托盘可用；雨循环卡片出现在标签栏旁或其他合理位置。
- [x] 不支持的功能在设置页有明确说明，不静默失败。

详细记录见 `ai-docs/PHASE4_RESULTS.md`。

---

## 4. Phase 5：打包、测试、文档

### 4.1 Linux 打包

- [x] 新增 `packaging/linux/`：
  - `org.slugcatpet.SlugcatPet.desktop`
  - `slugcatpet.svg`
  - `install.sh`
  - `uninstall.sh`
  - `README.md`
- [x] 安装 KWin 脚本、desktop 文件、图标。
- [x] 不打包 Rain World 游戏素材，首次启动仍走 `gameassets` 导入。
- [x] 保留 `uv run slugcatpet` 源码运行方式。
- [x] `pyproject.toml` 增加 Linux classifier / 多平台描述。
- [x] wheel 包含 `kwin_script/metadata.json` 与 `contents/code/main.js`。
- [ ] 在干净用户环境完整运行一次 `install.sh`（本机下载 PySide6 超时，未完成）。

### 4.2 测试

- [x] 输入区域测试：猫/面板/拖拽状态并集、空区域 1×1、clamp（`test_wayland_regions.py`）。
- [x] 坐标测试：全局 → overlay → canvas，DPR 1.5/2.0，多屏（`test_wayland_backend.py`、`test_wayland_overlay.py`）。
- [x] KWin 桥测试：JSON 解析、全屏/输出过滤、热键 spec、服务注册失败降级。
- [x] overlay 布局测试：geometry、持久化迁移、clamp。
- [x] KWin 持久安装测试：kwinrc 文本、安装/卸载、metadata（`test_kwin_install.py`）。
- [x] KWin 集成本机脚本：`tools/kwin_integration_check.py`（临时安装/启用、`isScriptLoaded`、恢复配置）。
- [x] 现有 offscreen 单元回归保持通过（44 个测试）。
- [ ] 手动验收：点击穿透、拖猫、右键菜单、HUD/标签栏、托盘、全屏隐藏、音频。
- [ ] Windows 行为回归；`tests/behavior_check.py check` 需要本机 Rain World 素材，CI 只跑单元/静态检查。

### 4.3 光标写入（已完成本机验证）

- [x] `CursorHijack` 可插拔驱动：clip/setpos/busy/restore/release。
- [x] 临时全屏捕获面 `SlugcatPet Cursor Capture`；KWin 脚本保持置顶并排除窗口快照。
- [x] 坐标换算：内部物理坐标 → 全局逻辑 → 捕获面本地 → Qt frame 原点补偿。
- [x] `QApplication` override cursor 忙碌样式。
- [x] 能力门控：KWin 服务/脚本 + Qt 6.12 pointer-warp。
- [x] 单元测试：`tests/test_cursor_write.py`、KWin 脚本占位符测试。
- [x] 本机 KWin 验证：从桌面空白处启动 hold，KWin 探测到 `moved 569 1256`。
- [x] 焦点保持：overlay 首次映射和捕获面激活后，KWin 最终活动窗口恢复为原窗口。
- [x] 真实左/右键解除：uinput 注入 `BTN_LEFT`/`BTN_RIGHT`，按下后捕获面隐藏、忙碌光标恢复、劫持清空。
- [ ] 用真实猫行为（石头命中、升天、矛、Pyro/Riv 抓取）逐项验收。
- [ ] 多输出逃逸验收：指针移到另一输出后确认降级不崩溃、不把光标拉回。
- [ ] Rain World 全屏 + 光标劫持组合验收。

### 4.4 文档与 CI

- [x] README 增加 Linux 安装、KWin 集成、降级模式、已知限制。
- [x] 更新 `PORTABILITY_ANALYSIS.md` 的最终结论。
- [x] 新增 Wayland 故障排查（`packaging/linux/README.md`）：
  - KWin 脚本未加载
  - 光标不更新
  - 输入区域异常
  - 全屏检测失效
- [x] Linux CI：ruff、格式、单元测试、`params_doc --check`、导入冒烟、KWin 脚本 `node --check`。
- [x] Windows CI：ruff、格式、单元测试、`params_doc --check`、导入冒烟。
- [ ] Windows 完整行为回归（需要本机素材，保持手动）。
- [x] KWin 集成测试提供本地脚本 `tools/kwin_integration_check.py`，不要求 GitHub 托管 runner 有 Plasma 会话。

---

## 5. Phase 2 遗留清理

这些不阻塞 Phase 3，但建议排进收尾：

- [ ] 设置/音乐内部的皮肤、尾巴、音量弹层仍是 `Qt.Popup + mapToGlobal`。
- [ ] 首次启动 `SetupPanel` 在 overlay 创建之前运行，没有 transient parent。
- [x] overlay 首次显示抢焦点问题：KWin 脚本在 overlay 首次映射时把焦点还给原外部窗口；映射后 1 秒内的激活按映射处理，ControlHud 的后续激活仍保留。其他合成器未验证。
- [x] 托盘雨卡片已改为标签栏/光标/表盘/右下角锚点。
- [ ] 偶发 QtWayland 退出段错误（`QWaylandWindow::decoration`），尚未稳定复现。
- [x] 提交流程：
  - Phase 4 源码、测试和文档已单独提交；
  - `pyproject.toml`、`uv.lock` 的用户改动仍保持未提交。

---

## 6. 建议执行顺序

1. Phase 0–4 已完成；Phase 5 的光标写入、焦点/点击、Linux 打包、KWin 持久安装、desktop/图标、CI、README 已完成。
2. 在干净用户环境跑一次完整安装，并注销/登录验证持久脚本与自启。
3. 用 Rain World 实际全屏窗口、真实猫行为和多输出逃逸做最终验收。
4. 清理 Phase 2 遗留的 `Qt.Popup` 弹层、`SetupPanel` transient parent 和退出段错误。
5. 按阶段提交，`pyproject.toml` / `uv.lock` 的用户改动单独处理。

---

## 7. 当前仓库状态

- 测试应用使用隔离配置 `/tmp/opencode/phase3-home`、`XDG_CONFIG_HOME=/tmp/opencode/phase4-config`；验收脚本会临时加载/卸载 KWin 脚本。
- Phase 0–4 已提交；Wayland 光标写入、焦点/点击、Linux 打包、KWin 持久安装、CI 和文档已作为 Phase 5 的一部分提交；`pyproject.toml` 的打包相关改动与 `uv.lock` 的用户改动分开处理。
- 最近一次自动检查结果：
  - `uv run ruff check .`：通过
  - `uv run ruff format --check .`：通过
  - `uv run python -m unittest discover -s tests`：44 个测试通过
  - `uv run python tools/params_doc.py --check`：通过
  - `uv run python tools/kwin_integration_check.py`：PASS
- 本机 KWin 验收：临时捕获面 + `QCursor.setPos()` 已能把光标从 `(700,1500)` 移到 `(569,1256)`；忙碌样式状态为 true，释放后恢复。
- 持久 KWin 脚本：`metadata.json` 的 `KPackageStructure: KWin/Script` 修复后，`reconfigure` 能在 Plasma 6.8 中加载 `slugcatpet`；运行时脚本使用 `slugcatpet-runtime`，停用持久插件不会卸载当前会话。
