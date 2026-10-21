# Rain World 配乐选择性导入

- 日期：2026-10-21
- 状态：功能已实现，逻辑测试与本机提取冒烟通过
- 入口：音乐窗口「导入」菜单 →「从 Rain World 导入配乐…」；设置 → 声音 →「Rain World 配乐 / 导入…」

## 1. 需求

- 不再只固定提取 4 首场景曲，用户可以从 Rain World 游戏目录选择任意配乐导入。
- 入口可以随时打开，不要求重新走首次启动的素材导入。
- 二级窗口列出游戏内可选曲目，支持搜索和勾选，只导入选中的部分。
- 不改变 Windows 行为，不修改游戏文件。

## 2. 数据来源

配乐列表取两处的并集：

1. `RainWorld_Data/StreamingAssets/music/songs/*.mp3`
   - 某些安装里这些文件是 0 字节占位，但名字仍然有效。
2. `RainWorld_Data/StreamingAssets/AssetBundles/music_songs` 里的 `AudioClip` 名称。
   - 当前本机游戏得到 266 个曲名；其中 5 首只在资源包里。散文件目录里的 0 字节空占位如果资源包也没有同名曲，不会列为可用曲目。

散文件非空时直接复制。散文件缺失或为 0 字节时，从 `music_songs` 读取原始 FSB5：

- 常见 Vorbis setup 走现有 `fsb_to_ogg()`，输出 `.ogg`。
- 少数 Downpour/WMPA 曲目使用未知 setup，`fsb_to_ogg()` 会拒绝；此时退回 UnityPy 的 `AudioClip.samples` 解码为 `.wav`。这类文件明显更大，但能保证可选曲目都能导入。

游戏目录来源：

- 优先使用 `detect_install()` 已记住的路径；
- 找不到时，用户在窗口里选择包含 `RainWorld_Data` 的根目录；
- 选择成功后写入 `~/.slugcatpet/assets/game_path.txt`，下次直接复用。

## 3. 导入位置与播放器

- 目标目录：`~/.slugcatpet/music/Rain World/`，由 `_paths.rainworld_music_dir()` 创建。
- 导入完成后只把本次选中的文件传给 `MusicPlayer.add_paths(..., record=False)`：
  - 不把 266 个文件路径逐条写进 `music_sources`；
  - `MusicPlayer.rescan()` 本来就会递归扫描 `user_music_dir()`，所以重启后仍能找到；
  - 已移出列表的曲目仍受 `music_hidden` 约束，不会被重新加回。
- 导入的曲目作为普通用户曲目显示，不进入固定的 4 首「游戏配乐」组。
- 再次打开窗口时，已存在于目标目录的曲目显示「已导入」，但仍可勾选以重新加入播放列表。

## 4. 实现位置

- `slugcatpet/gameassets.py`
  - `game_music_names(install)`：合并散文件与资源包名称并自然排序。
  - `is_game_install(path)`：判断用户选择的是不是游戏根目录。
  - `remember_install(path)`：保存手动选择的路径。
  - `game_music_imported(name, out_dir)`：判断目标目录里是否已有非空文件。
  - `extract_music(..., out_dir=, progress=)`：选择性提取、进度回调、`out_dir` 模式不写 `.format` 标记。
  - `_bundle_decoded()`：未知 Vorbis setup 的 UnityPy 解码兜底。
- `slugcatpet/ui/panels/gamemusic.py`
  - `RainWorldMusicDialog`：搜索、全选/全不选/只选未导入、已导入标记、后台提取线程和进度条。
  - 提取期间禁止关闭，避免销毁仍在运行的 `QThread`。
- `slugcatpet/ui/panels/musicpanel.py`
  - 「导入」菜单包含音乐文件、文件夹、Rain World 配乐三项。
- `slugcatpet/ui/panels/settings.py`
  - 声音区增加「Rain World 配乐 / 导入…」，复用同一窗口。
- `slugcatpet/i18n.py`
  - 中英文案。
- `tests/test_game_music.py`
  - 自然排序、空文件判断、选择性复制、跳过已有、FSB 兜底、目录识别。

## 5. 验证记录

- `uv run python -m unittest tests.test_game_music -v`：8 个测试通过。
- 全量单元测试：56 个通过（含新增 8 个）。
- `ruff check` / `ruff format --check`：通过。
- 本机游戏扫描：266 首，自然排序正常。
- 本机提取 `RW_8 - Sundown`：输出 1,676,475 字节 `.ogg`。
- 本机提取仅资源包曲目 `RWTW_WeaverAura`、`WMPA_Calcification`：分别输出约 15 MB、13 MB `.wav`，验证未知 setup 兜底。
- offscreen 对话框冒烟：列表加载、全选、搜索过滤、后台导入信号、线程退出均正常。
- GitHub Actions Linux / Windows：提交 `511fdc7` 成功。

## 6. 限制

- 资源包内未知 setup 的曲目需要解码成 wav，文件更大、提取稍慢。
- 提取期间窗口不能关闭；没有取消按钮。
- 二级窗口不做试听，避免和播放器争用 `QMediaPlayer`。
- 游戏更新后点「重新读取」即可刷新曲目列表。
