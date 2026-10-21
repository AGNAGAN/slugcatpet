# 本地验收与探测脚本

- 来源：`/tmp/opencode/`
- 整理日期：2026-10-21
- 用途：保存原生 Wayland / KWin 移植过程中的可复现验收脚本、KWin 探测脚本和关键结果日志。
- 说明：这些文件**不是应用运行时代码**，不会进入 wheel；`pyproject.toml` 的 Ruff 配置已排除本目录，避免历史脚本影响 CI。

## 目录

```text
verification/
├── scripts/                  # 142 个 Python/JS 探测与验收脚本
├── logs/                     # 选出的关键结果日志
│   ├── live/                 # 重跑脚本时的新日志输出目录
│   └── shutdown-matrix.tar.gz
└── fixtures/
    └── phase3-home/          # 隔离的 SLUGCATPET_HOME（app.json、按键、皮肤说明）
```

### `scripts/`

保留了 `/tmp/opencode` 里的 Python/JS 脚本，包括：

- 通用输入/光标辅助：`uinput_mouse.py`、`uinput_keyboard.py`、`mouse_to_hdmi.py`、`mouse_escape*.py`、`mouse_click*.py`、`cursor_read.py`。
- Phase 0：`phase0_*`、`kwin_*`、`mask_probe*`、`dpr_probe.*`、托盘/布局探测。
- Phase 1：`phase1_*` 单表面、输入区域、焦点、绝对指针前置验证。
- Phase 3/4：全屏、窗口快照、输出切换、transient 窗口探测。
- Phase 5：`test_pet_cursor.py`、`test_cursor_focus_click.py`、`test_capture_events.py`、`test_multi_output_escape.py`、`test_output_*.py`、`test_spear_*.py` 等。

脚本里的原 `/tmp/opencode/` 引用已改为：

- 辅助脚本 → `verification/scripts/`
- 运行日志 → `verification/logs/live/`

脚本统一平铺，是因为多个脚本会互相调用；请从仓库根目录运行。

### `logs/`

保留了各阶段的关键结果日志，例如：

- Phase 0：`phase0_wayland.log`、`phase0_click.log`、`phase0_edp.log`、`phase0_panels.log`、托盘/DPR/DBus 探测。
- Phase 1：`phase1_preconditions.log`、`phase1_mask_click.log`、`phase1_ctrl.log`、`phase1_backend.log`、`phase1_cursor.log`。
- Phase 2：崩溃回溯和退出段错误调查：`phase2-gdb*.log`、`phase2-seg.log`。
- Phase 3：热键、窗口列表、KWin DBus 日志。
- Phase 5：光标写入、焦点保持、点击解除、多输出逃逸、输出切换/DPR、自由长矛输入区域日志。

较大的原始日志以 `.gz` 保存：

- `phase3-dbus-start.log.gz`
- `phase4-app5.err.gz`
- `slugcatpet-run.log.gz`
- `build-wheel.log.gz`
- `wayland-realclick2.log.gz`
- `wayland-realright.log.gz`
- `wayland-capturewarpclick.log.gz`

`shutdown-matrix.tar.gz` 保存退出段错误排查时的重复实验日志。日志中的本机绝对路径已替换为 `/home/user`，测试窗口标题已脱敏。

### `fixtures/phase3-home/`

这是 Phase 3/4/5 使用的隔离配置，包含 4 只猫的 `app.json`、`keybinds.json`、皮肤说明和当时生成的 KWin 脚本。建议复制到 `/tmp` 后再运行，避免脚本修改存档：

```bash
rm -rf /tmp/slugcatpet-verify-home
cp -a verification/fixtures/phase3-home /tmp/slugcatpet-verify-home
export SLUGCATPET_HOME=/tmp/slugcatpet-verify-home
export XDG_CONFIG_HOME=/tmp/slugcatpet-verify-config
mkdir -p "$XDG_CONFIG_HOME"
```

## 运行示例

```bash
# 需要当前会话为 KWin Wayland，且允许脚本移动真实指针
uv run python verification/scripts/test_pet_cursor.py
uv run python verification/scripts/test_cursor_focus_click.py
uv run python verification/scripts/test_multi_output_escape.py
```

注意：

- 多数脚本把目标输出写死为 `HDMI-A-1`，没有该输出时需要先改脚本里的 `params["output"]`。
- 光标验收会移动真实鼠标并短暂创建全屏捕获面；不要在正在操作其他窗口时运行。
- `mouse_*` / `uinput_*` 脚本需要 `/dev/uinput` 写权限。
- KWin 探测脚本会把输出发到 `verification/logs/live/`；原有 `logs/` 文件不会被覆盖。
- 这些脚本是历史验收工具，不替代 `tests/` 下的自动回归测试。

## 相关文档

- `ai-docs/PHASE0_RESULTS.md`
- `ai-docs/PHASE1_RESULTS.md`
- `ai-docs/PHASE2_RESULTS.md`
- `ai-docs/PHASE3_RESULTS.md`
- `ai-docs/PHASE4_RESULTS.md`
- `ai-docs/PHASE5_CURSOR_WRITE.md`
- `ai-docs/PHASE5_PACKAGING.md`
- `ai-docs/REMAINING_WORK.md`
