Windows 桌面宠物：让 Rain World 的蛞蝓猫住在你的屏幕上。exe 见 release 压缩包。

演示视频合集：https://space.bilibili.com/1810584454/lists?sid=8504199

RainWorld里控制蛞蝓猫各个bodychunk拼接和行动的质点系统是C#写的，反编译后参考常量和主要函数就能足够相似的模拟。但粒子shader等效果难以复现原游戏渲染，又为了提升桌宠性能，所以我做了大量简化。

## 运行要求

- Windows 10 / 11
- Python 3.12+
- 电脑上装了 Rain World 和 Downpour DLC。第一次启动时要从游戏里读取图像。

## 安装与运行

```powershell
pip install PySide6 UnityPy numpy Pillow
python run_slugcatpet.py
```

也可以用 uv：`uv sync` 后 `uv run run_slugcatpet.py`。

第一次启动时选一下 Rain World 的安装目录，程序会把要用的图像和几首游戏配乐提取到 `~/.slugcatpet/assets`。

## Linux（KDE Plasma / Wayland）

需要 KDE Plasma 6 / KWin 6（已在 Plasma 6.8 测试）、Wayland 会话、Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。光标写入还需要 Qt 6.12+ 和合成器的 `wp_pointer_warp_v1`。

```bash
./packaging/linux/install.sh
```

安装后从应用菜单启动 **SlugcatPet**，或运行 `slugcatpet`。首次启动同样需要选择 Rain World 目录。

KWin 集成（置顶、全屏检测、挡雨窗口、全局热键）在设置 → **Wayland / KWin** 中显式勾选「登录后自动加载 KWin 脚本」。勾选后才会把脚本装到 `~/.local/share/kwin/scripts/slugcatpet` 并修改 `kwinrc`；当前会话始终有运行时脚本。GNOME/Sway 可以使用，但上述能力会降级。

Wayland 的光标抢取是 **best-effort**，不是系统级锁定；左/右键单击会解除，指针持续移到其他输出时也会结束抢取并留在新输出。详细限制见 [`ai-docs/PHASE5_CURSOR_WRITE.md`](ai-docs/PHASE5_CURSOR_WRITE.md)。安装/卸载和故障排查见 [`packaging/linux/README.md`](packaging/linux/README.md)。

本地 Wayland/KWin 验收脚本、隔离配置和关键结果日志整理在 [`verification/`](verification/README.md)，不属于应用运行时代码。

## 音乐

音乐窗口的「导入」菜单里可以选「从 Rain World 导入配乐…」：程序会读取当前游戏目录中的全部配乐，在弹出的二级窗口中搜索、勾选，再把选中的曲目复制到 `~/.slugcatpet/music/Rain World`，不会修改游戏文件。设置 → **声音** → **Rain World 配乐** 也能打开同一个窗口。少数资源包曲目会解码成 wav，体积比 ogg 大。

## 皮肤

可以用 Dress My Slugcat 的皮肤。创意工坊里订阅的会自动出现，别人发给你的放进皮肤文件夹（设置 → 打开皮肤文件夹）就行。
在设置里点猫旁边的「外观」，可以换皮肤、改颜色、开关配件（疤、鳃）。头、脸、身体、手臂、臀、腿、尾巴还能各用不同的皮肤，也能单独设颜色、调尾巴形状。皮肤格式和画法见 [Dress My Slugcat](https://steamcommunity.com/sharedfiles/filedetails/?id=2948971756)。

## 改代码

结构见 [ai-docs/ARCHITECTURE.md](ai-docs/ARCHITECTURE.md)，加角色见 [ai-docs/CHARACTERS.md](ai-docs/CHARACTERS.md)，参数见 [ai-docs/PARAMS.md](ai-docs/PARAMS.md)。
改完跑一下 `python tests/behavior_check.py check`，确认原有的猫行为没变。格式用 ruff：`uv run ruff format` / `uv run ruff check`。

## 素材与版权说明

- 本仓库不包含任何 Rain World 游戏素材。全部游戏图像和音乐在你本机、从你自己的正版安装中提取。
- 皮肤归各自的作者所有。本程序只在你本机读取皮肤，不会打包或分发。
- 此项目为粉丝项目，Rain World 及相关名称、美术均归其权利人所有。
- 本仓库代码以 MIT 许可发布（见 [LICENSE](LICENSE)）；该许可仅覆盖本仓库代码，不授予任何游戏素材相关权利。
- `slugcatpet/audio/fsbogg.py` 部分改写自 [python-fsb5](https://github.com/HearthSim/python-fsb5)（MIT，Simon Pinfold）；`vorbis_setups.py` 中的数据由 libvorbis（BSD，Xiph.Org）生成。

---

A Windows desktop pet that puts Rain World's slugcats on your screen. The .exe is in the release zip.

Demo videos (Bilibili): https://space.bilibili.com/1810584454/lists?sid=8504199

The mass-point system in Rain World that controls the connection and movement of the slugcat's various body chunks is written in C#. After decompiling it, I referred to its constants and main functions, which was enough to create a sufficiently similar simulation. However, effects like particle shaders are hard to replicate to match the original game's rendering, and to boost the desktop pet's performance, I made extensive simplifications.

## Requirements

- Windows 10 / 11
- Python 3.12+
- Rain World and the Downpour DLC installed. The first launch reads images from the game.

## Install and run

```powershell
pip install PySide6 UnityPy numpy Pillow
python run_slugcatpet.py
```

With uv: `uv sync`, then `uv run run_slugcatpet.py`.

On first launch, pick your Rain World install folder. The images and a few game music tracks the app needs are extracted to `~/.slugcatpet/assets`.

## Linux (KDE Plasma / Wayland)

Requires KDE Plasma 6 / KWin 6 (tested on Plasma 6.8), a Wayland session, Python 3.12+, and [uv](https://docs.astral.sh/uv/). Cursor writing additionally needs Qt 6.12+ and `wp_pointer_warp_v1` from the compositor.

```bash
./packaging/linux/install.sh
```

Launch **SlugcatPet** from the application menu, or run `slugcatpet`. The first launch still asks for your Rain World directory.

Enable the KWin integration explicitly in Settings → **Wayland / KWin** → **Load KWin script at login**. That installs the script to `~/.local/share/kwin/scripts/slugcatpet` and updates `kwinrc`; the current session always uses a runtime script. GNOME and Sway work in a degraded mode without topmost, fullscreen detection, rain shelters, or global hotkeys.

Cursor grabbing on Wayland is **best-effort**, not a system-level pointer lock; left/right click releases it, and sustained movement to another output ends the grab and leaves the pointer there. See [`ai-docs/PHASE5_CURSOR_WRITE.md`](ai-docs/PHASE5_CURSOR_WRITE.md) for limitations and [`packaging/linux/README.md`](packaging/linux/README.md) for install/uninstall and troubleshooting.

## Skins

Dress My Slugcat skins work. Workshop subscriptions show up on their own; put skins you get elsewhere in the skins folder (Settings → Open skins folder).
Click "Appearance" next to a cat in Settings to change its skin, colors and accessories (scar, gills). Head, face, body, arms, hips, legs and tail can each use a different skin and color, and the tail shape is adjustable. Skin format and drawing: [Dress My Slugcat](https://steamcommunity.com/sharedfiles/filedetails/?id=2948971756).

## Changing the code

Layout: [ai-docs/ARCHITECTURE.md](ai-docs/ARCHITECTURE.md). Adding characters: [ai-docs/CHARACTERS.md](ai-docs/CHARACTERS.md). Parameters: [ai-docs/PARAMS.md](ai-docs/PARAMS.md). These are in Chinese.
After a change, run `python tests/behavior_check.py check` to make sure the existing cats still behave the same. Format with ruff: `uv run ruff format` / `uv run ruff check`.

## Assets and copyright

- This repository contains no Rain World assets. All game images and music are extracted on your machine from your own copy.
- Skins belong to their authors. The app only reads them on your machine and never bundles or redistributes them.
- This is a fan project. Rain World and all related names and artwork belong to their respective owners.
- The code is released under the MIT license (see [LICENSE](LICENSE)). It covers this repository's code only and grants no rights to any game assets.
- `slugcatpet/audio/fsbogg.py` is partly adapted from [python-fsb5](https://github.com/HearthSim/python-fsb5) (MIT, Simon Pinfold); the data in `vorbis_setups.py` was generated with libvorbis (BSD, Xiph.Org).
