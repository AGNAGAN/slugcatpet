# Phase 5：Linux 打包、KWin 安装与 CI

- 日期：2026-10-21
- 范围：Phase 5 的 Linux 打包、KWin 脚本持久安装/启用、桌面入口/图标、Linux/Windows CI、README 与故障排查。
- 结论：**Linux 打包与 KWin 持久安装已实现；持久脚本能在 Plasma 6.8 / KWin 6.8 下通过 `reconfigure` 加载，运行时脚本与持久插件使用不同 ID，切换开关不会破坏当前会话。**

---

## 1. 交付内容

### 1.1 Linux 应用打包

新增：

```text
packaging/linux/
├── README.md
├── install.sh
├── uninstall.sh
├── org.slugcatpet.SlugcatPet.desktop
└── slugcatpet.svg
```

`install.sh`：

- 用 `uv tool install --force --python 3.12 <repo>` 安装到隔离环境；
- 把启动器放到 `$PREFIX/bin`（默认 `~/.local/bin`）；
- 安装图标到 `$XDG_DATA_HOME/icons/hicolor/scalable/apps/slugcatpet.svg`；
- 安装 desktop 文件到 `$XDG_DATA_HOME/applications/`，并把 `Exec`/`TryExec` 改成绝对启动器路径；
- 不修改 `kwinrc`，KWin 集成保持显式选择；
- 支持 `PREFIX`、`UV_TOOL_BIN_DIR`、`XDG_DATA_HOME`、`XDG_CONFIG_HOME`。

`uninstall.sh`：

- `uv tool uninstall slugcatpet`；
- 删除 desktop 文件、图标和 `~/.local/share/kwin/scripts/slugcatpet`；
- 用 `kwriteconfig6` 写 `slugcatpetEnabled=false`，并 `unloadScript` + `reconfigure`；
- 保留 `~/.slugcatpet`（设置、素材、皮肤、日志）。

不打包任何 Rain World 游戏素材；首次启动仍由 `gameassets` 从本机正版安装提取。

### 1.2 自启对打包安装的适配

`slugcatpet/platform/autostart.py` 现在区分：

- 源码仓库：`base_dir()/run_slugcatpet.py` 存在时，继续写 `python run_slugcatpet.py`；
- `uv tool` / wheel 安装：使用 `sys.argv[0]` 的 `slugcatpet` 启动器或 `shutil.which("slugcatpet")`；
- 安装式的 `Path=` 使用用户主目录，不再误用 `site-packages` 或解释器目录。

这样从应用菜单启动和开机自启都会指向同一个 console script。

### 1.3 KWin 持久安装/启用

新增 `slugcatpet/platform/wayland/kwin_install.py`：

- 安装目录：`$XDG_DATA_HOME/kwin/scripts/slugcatpet`；
- 文件：`metadata.json`、`contents/code/main.js`；
- 配置：`$XDG_CONFIG_HOME/kwinrc` 的 `[Plugins]` 组写入
  `slugcatpetEnabled=true/false`；
- 文本更新是纯函数，保留其他分组和键；
- `reconfigure()` / `unload_script()` 延迟导入 QtDBus，便于单元测试；
- `uninstall()` 删除插件目录并关闭配置键。

`metadata.json` 必须包含：

```json
"KPackageStructure": "KWin/Script"
```

这是本机实测发现的必要字段。缺少它时 KWin 6.8 会报：

```text
KPackageStructure ... does not match requested format "KWin/Script"
```

并把脚本视为未加载。

设置页在 **设置 → Wayland / KWin** 增加「登录后自动加载 KWin 脚本」开关，并显示：

- 未安装；
- 已安装但登录后不加载；
- 已安装并启用。

只有用户勾选后才会写 `kwinrc`。默认关闭；当前会话始终使用运行时脚本。

### 1.4 运行时插件与持久插件分离

原先运行时 `loadScript()` 与持久插件都叫 `slugcatpet`。实测发现：停用持久插件后，KWin 的 `reconfigure` 会把同名运行时脚本一起按禁用状态卸载，`loadScript()` 返回成功但 `isScriptLoaded` 仍为 false。

现在：

- 持久插件：`slugcatpet`（来自用户脚本目录）；
- 运行时插件：`slugcatpet-runtime`（应用每次启动写入 `~/.slugcatpet/kwin/slugcatpet.js`）；
- `_load_script()` 先卸载 `slugcatpet-runtime` 和可能由登录加载的 `slugcatpet`，再加载运行时脚本；
- `set_integration_enabled()` 写配置、`reconfigure`，700 ms 后重新加载运行时脚本；
- 停用持久插件不会再影响当前会话的运行时脚本。

设置页开关只改变“下次登录是否自动加载”；本次会话继续由运行时脚本提供几何、置顶、全屏检测、挡雨窗口和热键。

### 1.5 CI 与文档

新增：

- `.github/workflows/linux.yml`：ruff、格式、48 个单元测试、`params_doc --check`、导入冒烟、KWin 脚本渲染后 `node --check`；
- `.github/workflows/windows.yml`：ruff、格式、单元测试、`params_doc --check`、导入冒烟；
- README 增加 Linux 安装、KWin 集成、降级模式、光标限制和故障排查入口；
- `packaging/linux/README.md` 给出安装/卸载、KWin 状态检查、光标/输入/全屏排查。

Windows 的完整行为回归仍需要本机 Rain World 素材，CI 只跑单元/静态检查；完整命令仍是：

```powershell
python tests/behavior_check.py check
```

---

## 2. 验证记录

### 2.1 自动检查

```text
uv run ruff check .                         通过
uv run ruff format --check .                通过（292 files）
uv run python -m unittest discover -s tests 48 tests OK
uv run python tools/params_doc.py --check   通过
bash -n packaging/linux/install.sh          通过
bash -n packaging/linux/uninstall.sh        通过
desktop-file-validate ...desktop            无错误
```

GitHub Actions（公开仓库实际运行）：

```text
Linux   run 1/2/3  success
Windows run 1/2/3  success
```

对应提交 `10428d3`、`a640bb6`、`b7b8ef6`。

### 2.2 wheel 内容

`uv build --wheel` 生成的 wheel 包含：

```text
slugcatpet/platform/wayland/kwin_script/metadata.json
slugcatpet/platform/wayland/kwin_script/contents/code/main.js
```

因此 `uv tool install` / 打包安装后，设置页仍能读取并安装 KWin 脚本。

### 2.3 KWin 持久安装实测

本机 Plasma 6.8 / KWin 6.8：

```bash
uv run python tools/kwin_integration_check.py
# loaded after enable: True
# PASS
```

该脚本会临时写入真实 `kwinrc` 和用户脚本目录，验证 `isScriptLoaded("slugcatpet")`，结束后恢复 `kwinrc`、卸载脚本并 `reconfigure`。

### 2.4 运行时/持久切换实测

用临时 PetWindow 运行：

```text
before           IntegrationState(installed=False, enabled=False)
enable           IntegrationState(installed=True,  enabled=True)
loaded runtime   True
disable          IntegrationState(installed=True,  enabled=False)
loaded runtime   True
```

停用后 `slugcatpet-runtime` 仍保持加载；持久插件 `slugcatpet` 不重复运行。测试结束后配置恢复、脚本目录为空。

### 2.5 桌面文件

`desktop-file-validate` 仅一开始提示 `Game;Utility;` 同时包含两个主分类；已改为 `Categories=Game;`，现在无错误。

---

## 3. 尚未完成的最终验收

1. 在干净用户环境跑一次完整 `./packaging/linux/install.sh`。本机真实 `uv tool install` 已完成依赖解析和构建，但下载 PySide6（约 250 MB）超时；用隔离 HOME/XDG 和假 `uv` 验证了 install/uninstall 的启动器、desktop、图标路径、`desktop-file-validate` 与卸载清理。wheel 内容和启动逻辑也已单独验证。
2. 注销/重新登录，确认：
   - 持久脚本在应用启动前加载；
   - 应用启动后用当前输出几何重新加载运行时脚本；
   - 设置/音乐/托盘正常。
3. 用 Rain World 实际全屏窗口做一次最终验收。
4. 真实猫行为光标验收：石头命中、升天、矛、Pyro/Riv 抓取。
5. ~~多输出逃逸~~：已用 uinput 持续移动到 eDP-1 验证，捕获面 `leaveEvent` 结束劫持，光标留在新输出；详见 `PHASE5_CURSOR_WRITE.md`。
6. Windows 本机跑 `tests/behavior_check.py check`。

---

## 4. 已知限制

1. **登录时旧几何**：持久脚本按上次启用时写入的 `main.js` 加载；应用启动后立即重新渲染运行时脚本。若应用没有自启，持久脚本会停留在旧几何，直到应用启动或重新启用。
2. **必须显式启用**：安装脚本不会自动修改 `kwinrc`；需要用户在设置页勾选。
3. **只在 KWin 6 上完整工作**：GNOME/Sway 没有 KWin 桥，置顶、全屏检测、挡雨、全局热键、光标读取/写入会降级。
4. **光标仍是 best-effort**：不是系统级 pointer lock；依赖临时捕获面和 `wp_pointer_warp_v1`。
5. **CI 无 Plasma**：KWin 集成测试只提供本机脚本 `tools/kwin_integration_check.py`，不在 GitHub 托管 runner 上运行。

---

## 5. 涉及文件

- `packaging/linux/`
- `.github/workflows/linux.yml`
- `.github/workflows/windows.yml`
- `slugcatpet/platform/wayland/kwin_install.py`
- `slugcatpet/platform/wayland/kwin_bridge.py`
- `slugcatpet/platform/wayland/kwin_script/metadata.json`
- `slugcatpet/platform/autostart.py`
- `slugcatpet/ui/panels/settings.py`
- `slugcatpet/i18n.py`
- `tools/kwin_integration_check.py`
- `tests/test_kwin_install.py`
- `tests/test_wayland_backend.py`
- `tests/test_phase4.py`
- `README.md`
