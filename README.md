Windows 桌面宠物：让 Rain World 的蛞蝓猫住在你的屏幕上。exe 见 release 压缩包。

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

## 皮肤

可以用 Dress My Slugcat 的皮肤。创意工坊里订阅的会自动出现，别人发给你的放进皮肤文件夹（设置 → 打开皮肤文件夹）就行。
在设置里点猫旁边的「外观」，可以换皮肤、改颜色、开关配件（疤、鳃）。皮肤格式和画法见 [Dress My Slugcat](https://steamcommunity.com/sharedfiles/filedetails/?id=2948971756)。

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

## Skins

Dress My Slugcat skins work. Workshop subscriptions show up on their own; put skins you get elsewhere in the skins folder (Settings → Open skins folder).
Click "Appearance" next to a cat in Settings to change its skin, colors and accessories (scar, gills). Skin format and drawing: [Dress My Slugcat](https://steamcommunity.com/sharedfiles/filedetails/?id=2948971756).

## Changing the code

Layout: [ai-docs/ARCHITECTURE.md](ai-docs/ARCHITECTURE.md). Adding characters: [ai-docs/CHARACTERS.md](ai-docs/CHARACTERS.md). Parameters: [ai-docs/PARAMS.md](ai-docs/PARAMS.md). These are in Chinese.
After a change, run `python tests/behavior_check.py check` to make sure the existing cats still behave the same. Format with ruff: `uv run ruff format` / `uv run ruff check`.

## Assets and copyright

- This repository contains no Rain World assets. All game images and music are extracted on your machine from your own copy.
- Skins belong to their authors. The app only reads them on your machine and never bundles or redistributes them.
- This is a fan project. Rain World and all related names and artwork belong to their respective owners.
- The code is released under the MIT license (see [LICENSE](LICENSE)). It covers this repository's code only and grants no rights to any game assets.
- `slugcatpet/audio/fsbogg.py` is partly adapted from [python-fsb5](https://github.com/HearthSim/python-fsb5) (MIT, Simon Pinfold); the data in `vorbis_setups.py` was generated with libvorbis (BSD, Xiph.Org).
