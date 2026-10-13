"""界面文案中英两套 + 运行期取串。默认语言随系统界面语言，设置里可以切换。"""

from __future__ import annotations
import locale
import os
import sys


def _system_is_zh() -> bool:
    if sys.platform == "win32":
        try:
            import ctypes

            return ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x04  # LANG_CHINESE
        except Exception:
            pass
    name = (locale.getlocale()[0] or "").lower()
    return name.startswith(("zh", "chinese"))


def _detect_lang() -> str:
    env = os.environ.get("SLUGCATPET_LANG", "").strip().lower()
    if env in ("zh", "en"):
        return env
    return "zh" if _system_is_zh() else "en"


LANG = _detect_lang()


def set_lang(lang: str) -> None:
    """切换语言；界面要由调用方重建。"""
    global LANG
    if lang in ("zh", "en"):
        LANG = lang


_STR = {
    "app_title": {"zh": "蛞蝓猫桌宠", "en": "Slugcat Pet"},
    "setup_importing": {"zh": "正在导入素材…", "en": "Importing assets…"},
    "setup_hint_init": {
        "zh": "首次启动需从你的游戏读取画面，请稍候",
        "en": "First launch needs to read the picture from your game, please wait",
    },
    "setup_hint_busy": {
        "zh": "首次启动需从你的游戏读取素材，请稍候。未来不再需要读取",
        "en": "First launch needs to read assets from your game, please wait. Won't be needed again in the future",
    },
    "setup_hint_error": {
        "zh": "点【选择 RainWorld 文件夹】手动指定：选中的文件夹里应能看到 RainWorld.exe 和 RainWorld_Data 文件夹",
        "en": "Click [Select RainWorld folder] to specify manually: the chosen folder should contain RainWorld.exe and the RainWorld_Data folder",
    },
    "setup_quit": {"zh": "退出", "en": "Quit"},
    "setup_pick": {"zh": "选择 RainWorld 文件夹", "en": "Select RainWorld folder"},
    "setup_unexpected": {"zh": "导入时发生意外错误：{e}", "en": "Unexpected error during import: {e}"},
    "tip_vpole": {"zh": "放竖杆", "en": "Place vertical pole"},
    "tip_hpole": {"zh": "放横杆", "en": "Place horizontal pole"},
    "tip_fruit": {"zh": "放果子", "en": "Place fruit"},
    "tip_stone": {"zh": "放石头", "en": "Place stone"},
    "tip_lamp": {"zh": "放灯笼", "en": "Place lantern"},
    "tip_slimemold": {"zh": "放黏菌", "en": "Place slime mold"},
    "tip_batfly": {"zh": "放蝙蝠", "en": "Place batfly"},
    "tip_remove": {"zh": "移除单个物品", "en": "Remove one item"},
    "tip_clear": {"zh": "清除可交互实体", "en": "Clear placed items"},
    "toast_max_fruit": {"zh": "场上最多 {n} 个果子", "en": "At most {n} fruits on the field"},
    "toast_max_stone": {"zh": "场上最多 {n} 个石头", "en": "At most {n} stones on the field"},
    "toast_max_slimemold": {"zh": "场上最多 {n} 个黏菌", "en": "At most {n} slime molds on the field"},
    "toast_max_batfly": {"zh": "场上最多 {n} 只蝙蝠", "en": "At most {n} batflies on the field"},
    "toast_max_vpole": {"zh": "场上最多 {n} 根竖杆", "en": "At most {n} vertical poles on the field"},
    "toast_max_hpole": {"zh": "场上最多 {n} 根横杆", "en": "At most {n} horizontal poles on the field"},
    "place_hint": {
        "zh": "左键放置，右键或 Esc 退出",
        "en": "Left-click to place, right-click or Esc to stop",
    },
    "place_hint_remove": {
        "zh": "左键移除，右键或 Esc 退出",
        "en": "Left-click to remove, right-click or Esc to stop",
    },
    "toast_no_object": {"zh": "场上没有物体", "en": "No objects on the field"},
    "btn_quit_app": {"zh": "退出程序", "en": "Quit program"},
    "dlg_confirm_title": {"zh": "确认", "en": "Confirm"},
    "dlg_kill_text": {"zh": "确定要杀死 {name} 吗？", "en": "Are you sure you want to kill {name}?"},
    "dlg_kill_yes": {"zh": "杀死", "en": "Kill"},
    "dlg_kill_no": {"zh": "取消", "en": "Cancel"},
    "hud_karma": {"zh": "业力", "en": "Karma"},
    "hud_stamina": {"zh": "体力", "en": "Stamina"},
    "hud_satiety": {"zh": "饱食", "en": "Satiety"},
    "hud_affection": {"zh": "好感", "en": "Affection"},
    "hud_cold": {"zh": "寒冷", "en": "Cold"},
    "hud_air": {"zh": "氧气", "en": "Air"},
    "hud_op_hint": {
        "zh": "右键蛞蝓猫或点击此行可操作",
        "en": "Right-click the slugcat or click this row to operate",
    },
    "variant_saint": {"zh": "圣徒", "en": "Saint"},
    "variant_rivulet": {"zh": "溪流", "en": "Rivulet"},
    "variant_survivor": {"zh": "白猫", "en": "Survivor"},
    "variant_monk": {"zh": "黄猫", "en": "Monk"},
    "variant_hunter": {"zh": "猎手", "en": "Hunter"},
    "variant_artificer": {"zh": "工匠", "en": "Artificer"},
    "variant_wip_note": {"zh": "（外观差异待后续）", "en": "(appearance differences TBD)"},
    "menu_kill_pet": {"zh": "杀掉该猫", "en": "Kill this cat"},
    "menu_reset_pet": {"zh": "重置该猫", "en": "Reset this cat"},
    "menu_reincarnating": {"zh": "转世中…", "en": "Reincarnating…"},
    "menu_open_settings": {"zh": "打开设置", "en": "Open settings"},
    "btn_music": {"zh": "音乐", "en": "Music"},
    "tray_music": {"zh": "音乐", "en": "Music"},
    "music_title": {"zh": "音乐", "en": "Music"},
    "music_empty": {
        "zh": "列表是空的，点「导入音乐」或把歌放进音乐目录",
        "en": "The list is empty. Import music or drop it into the music folder",
    },
    "music_import_files": {"zh": "导入音乐", "en": "Import"},
    "music_import_dir": {"zh": "导入文件夹", "en": "Import folder"},
    "music_open_folder": {"zh": "打开音乐目录", "en": "Open music folder"},
    "music_rescan": {"zh": "重新扫描", "en": "Rescan"},
    "music_back5": {"zh": "后退 5 秒", "en": "Back 5 s"},
    "music_forward5": {"zh": "前进 5 秒", "en": "Forward 5 s"},
    "music_play": {"zh": "播放 / 暂停", "en": "Play / pause"},
    "music_prev": {"zh": "上一首", "en": "Previous"},
    "music_next": {"zh": "下一首", "en": "Next"},
    "music_remove": {"zh": "移出列表", "en": "Remove"},
    "music_mode_order": {"zh": "列表循环", "en": "Repeat all"},
    "music_mode_shuffle": {"zh": "随机播放", "en": "Shuffle"},
    "music_mode_one": {"zh": "单曲循环", "en": "Repeat one"},
    "music_volume": {"zh": "音量", "en": "Volume"},
    "music_imported": {"zh": "导入了 {n} 首", "en": "Imported {n} track(s)"},
    "music_import_none": {"zh": "没找到音频文件", "en": "No audio files found"},
    "music_pick_files": {"zh": "选择音乐文件", "en": "Select music files"},
    "music_pick_dir": {"zh": "选择音乐文件夹", "en": "Select a music folder"},
    "music_no_selection": {"zh": "先选中一首", "en": "Select a track first"},
    "music_game_group": {"zh": "游戏配乐", "en": "Game music"},
    "music_game_fixed": {"zh": "游戏配乐不能移出列表", "en": "Game music can't be removed"},
    "settings_sound_section": {"zh": "声音", "en": "Sound"},
    "settings_mute_all": {"zh": "静音", "en": "Mute"},
    "settings_scene_music": {"zh": "场景配乐", "en": "Scene music"},
    "settings_scene_music_btn": {"zh": "配置…", "en": "Configure…"},
    "scene_col_scene": {"zh": "场景", "en": "Scene"},
    "scene_col_track": {"zh": "曲目", "en": "Track"},
    "scene_col_mode": {"zh": "模式", "en": "Mode"},
    "scene_col_volume": {"zh": "音量", "en": "Volume"},
    "scene_intro": {"zh": "开屏", "en": "Startup"},
    "scene_settings": {"zh": "打开设置时", "en": "Settings open"},
    "scene_none": {"zh": "无环境", "en": "No environment"},
    "scene_track_none": {"zh": "无", "en": "None"},
    "scene_track_missing": {"zh": "{name}（已丢失）", "en": "{name} (missing)"},
    "scene_my_music": {"zh": "我的音乐", "en": "My music"},
    "scene_mode_loop": {"zh": "循环", "en": "Loop"},
    "scene_mode_once": {"zh": "一次", "en": "Once"},
    "scene_mode_loop_tip": {"zh": "在该场景期间循环播放", "en": "Repeats while in this scene"},
    "scene_mode_once_tip": {
        "zh": "进入场景时播放一遍，放完即停",
        "en": "Plays once on entering the scene",
    },
    "scene_intro_once_tip": {"zh": "开屏只能播放一次", "en": "Startup music only plays once"},
    "scene_preview": {"zh": "试听", "en": "Preview"},
    "scene_volume_tip": {"zh": "点击调节，悬停时滚轮微调", "en": "Click to adjust, or scroll"},
    "settings_fullscreen": {"zh": "别的程序全屏时", "en": "When another app is full screen"},
    "settings_fs_hide": {"zh": "收起", "en": "Hide"},
    "settings_fs_sink": {"zh": "沉到屏幕底", "en": "Drop to the screen bottom"},
    "lang_name": {"zh": "中文", "en": "English"},
    "settings_lang": {"zh": "语言", "en": "Language"},
    "menu_hide_pet": {"zh": "收起这只", "en": "Hide this cat"},
    "menu_show_all": {"zh": "放出收起的猫", "en": "Show hidden cats"},
    "menu_control_pet": {"zh": "控制该猫", "en": "Control this cat"},
    "menu_exit_control": {"zh": "退出控制", "en": "Exit control"},
    "ctrlhud_title": {"zh": "控制中：{name}", "en": "Controlling: {name}"},
    "ctrlhud_paused": {"zh": "已暂停 · 点击继续", "en": "Paused · click to resume"},
    "ctrlhud_exit": {"zh": "退出控制 (Esc)", "en": "Exit control (Esc)"},
    "ctrlhud_keys": {"zh": "{move} 移动，{jump} 跳跃", "en": "{move} to move, {jump} to jump"},
    "settings_title": {"zh": "设置", "en": "Settings"},
    "settings_cats_section": {"zh": "蛞蝓猫", "en": "Slugcats"},
    "settings_add": {"zh": "添加", "en": "Add"},
    "settings_remove": {"zh": "移除", "en": "Remove"},
    "settings_max_pets": {"zh": "已到上限", "en": "Limit reached"},
    "settings_max_pets_label": {"zh": "最多同时在场", "en": "Max on screen"},
    "settings_hide_pet": {"zh": "收起", "en": "Hide"},
    "settings_show_pet": {"zh": "放出", "en": "Show"},
    "settings_min_pets": {"zh": "至少保留 1 只", "en": "Keep at least 1 cat"},
    "settings_remove_confirm": {"zh": "确定移除 {name}？", "en": "Remove {name}?"},
    "settings_env_section": {"zh": "环境", "en": "Environment"},
    "settings_env_none": {"zh": "无", "en": "None"},
    "settings_snow": {"zh": "暴风雪", "en": "Blizzard"},
    "settings_zerog": {"zh": "无重力", "en": "Zero gravity"},
    "settings_water": {"zh": "涨水", "en": "Flood"},
    "settings_water_depth": {"zh": "水深", "en": "Water depth"},
    "settings_show_hud": {"zh": "显示状态面板", "en": "Show status panel"},
    "settings_interact_section": {"zh": "交互", "en": "Interaction"},
    "settings_perf_section": {"zh": "性能", "en": "Performance"},
    "settings_sys_section": {"zh": "系统", "en": "System"},
    "refresh_top": {"zh": "重新置顶", "en": "Bring to front"},
    "settings_cursor_hijack": {"zh": "猫可以抢光标", "en": "Cats can grab the cursor"},
    "settings_cursor_shape": {"zh": "光标被抢时换成忙碌样式", "en": "Busy cursor while grabbed"},
    "settings_fps": {"zh": "帧率", "en": "Frame rate"},
    "settings_fps_auto": {"zh": "自动（{hz} FPS）", "en": "Auto ({hz} FPS)"},
    "settings_power_save": {"zh": "没动静时降低帧率", "en": "Lower frame rate when idle"},
    "settings_autostart": {"zh": "开机自动启动", "en": "Launch at startup"},
    "settings_pick_title": {"zh": "添加蛞蝓猫", "en": "Add a slugcat"},
    "settings_pick_cat": {"zh": "选择要添加的蛞蝓猫", "en": "Choose a slugcat to add"},
    "settings_ok": {"zh": "确定", "en": "OK"},
    "settings_cancel": {"zh": "取消", "en": "Cancel"},
    "settings_skins_section": {"zh": "外观", "en": "Appearance"},
    "settings_skins_open": {"zh": "打开皮肤文件夹", "en": "Open skins folder"},
    "settings_skins_scan": {
        "zh": "读取游戏 mods 与创意工坊里的皮肤",
        "en": "Read skins from game mods and the Workshop",
    },
    "settings_skins_status": {"zh": "已识别 {n} 个皮肤", "en": "{n} skins found"},
    "settings_skins_status_bad": {
        "zh": "，{n} 个问题（见加载报告）",
        "en": ", {n} problem(s) (see load report)",
    },
    "skin_missing_group": {
        "zh": "{group} 组缺 {n} 帧（如 {first}）→ 该部件用原版",
        "en": "{group} is missing {n} frame(s) (e.g. {first}) → original used for this part",
    },
    "skin_zip_fail": {"zh": "{name} 解压失败：{e}", "en": "Failed to unpack {name}: {e}"},
    "skin_err_meta_parse": {"zh": "metadata.json 读取失败：{e}", "en": "Could not read metadata.json: {e}"},
    "skin_err_meta_fields": {
        "zh": "metadata.json 缺少字段：{fields}",
        "en": "metadata.json is missing: {fields}",
    },
    "skin_err_id": {"zh": "id 过长或含控制字符", "en": "id is too long or contains control characters"},
    "skin_err_pack_size": {
        "zh": "图片总大小 {mb} MB 超过上限 {cap} MB",
        "en": "Images total {mb} MB, over the {cap} MB limit",
    },
    "skin_err_frames": {"zh": "共 {n} 帧，超过上限 {cap}", "en": "{n} frames, over the limit of {cap}"},
    "skin_err_dup_id": {
        "zh": "id「{id}」与 {other} 重复，已跳过",
        "en": 'id "{id}" duplicates {other}; skipped',
    },
    "skin_warn_atlas_bad": {"zh": "{file} 读取失败：{e}", "en": "Could not read {file}: {e}"},
    "skin_warn_atlas_big": {
        "zh": "{file} 尺寸 {w}×{h} 超过上限 {cap}，已跳过",
        "en": "{file} is {w}×{h}, over the {cap} limit; skipped",
    },
    "skin_warn_empty": {
        "zh": "没有任何完整部件组，也没有颜色设置",
        "en": "No complete part group and no color settings",
    },
    "skin_warn_color": {
        "zh": "{group} 的颜色「{v}」无法识别（用 #RRGGBB）",
        "en": '{group} color "{v}" not recognized (use #RRGGBB)',
    },
    "skin_warn_extent": {
        "zh": "{group} 组的图案离锚点 {ext}px，超过上限 {cap}px → 该部件用原版",
        "en": "{group} art reaches {ext}px from its anchor, over the {cap}px limit → original used",
    },
    "look_button": {"zh": "外观", "en": "Appearance"},
    "look_skin": {"zh": "皮肤", "en": "Skin"},
    "look_color": {"zh": "颜色", "en": "Colors"},
    "look_default": {"zh": "默认", "en": "Default"},
    "look_custom": {"zh": "自定", "en": "Custom"},
    "look_body": {"zh": "体色", "en": "Body"},
    "look_face": {"zh": "脸色", "en": "Face"},
    "look_accessories": {"zh": "配件", "en": "Accessories"},
    "skin_original": {"zh": "原皮", "en": "Original"},
    "skin_done": {"zh": "完成", "en": "Done"},
    "btn_open_settings": {"zh": "打开设置", "en": "Open settings"},
    "already_running": {"zh": "蛞蝓猫桌宠已在运行", "en": "Slugcat Pet is already running"},
    "tray_settings": {"zh": "设置", "en": "Settings"},
    "tray_hud": {"zh": "显示/隐藏状态面板 (Ctrl+Alt+H)", "en": "Show/Hide status panel (Ctrl+Alt+H)"},
    "tray_quit": {"zh": "退出程序", "en": "Quit program"},
    "tray_abort": {"zh": "中止光标劫持 (Ctrl+Alt+Q)", "en": "Abort cursor hijack (Ctrl+Alt+Q)"},
    "tray_started": {
        "zh": "已启动。被超度的光标按 Ctrl+Alt+Q 解除；Ctrl+Alt+X 退出程序。",
        "en": "Launched. Press Ctrl+Alt+Q to release a salvaged cursor; Ctrl+Alt+X to quit the program.",
    },
    "err_atlas_missing": {
        "zh": "未找到游戏图集文件：{res}\n请选择 RainWorld 文件夹（其中应有 RainWorld.exe 和 RainWorld_Data 文件夹）。",
        "en": "Game atlas file not found: {res}\nPlease select the RainWorld folder (which should contain RainWorld.exe and the RainWorld_Data folder).",
    },
    "err_no_unitypy": {
        "zh": "缺少依赖 UnityPy，请先运行：pip install UnityPy",
        "en": "Missing dependency UnityPy, please run first: pip install UnityPy",
    },
    "err_base_fail": {
        "zh": "基础图集 rainWorld 提取失败，游戏文件可能损坏或版本不兼容。",
        "en": "Base atlas rainWorld extraction failed; game files may be corrupted or the version incompatible.",
    },
    "err_msc_missing": {
        "zh": "未找到 rainworldmsc 图集——Saint 属于 Downpour(More Slugcats) DLC，需要在 Steam 拥有该 DLC 才能导入。",
        "en": "rainworldmsc atlas not found — Saint belongs to the Downpour (More Slugcats) DLC; you need to own that DLC on Steam to import.",
    },
    "err_ui_fail": {
        "zh": "UI 图集 uiSprites 提取失败，游戏文件可能损坏或版本不兼容。",
        "en": "UI atlas uiSprites extraction failed; game files may be corrupted or the version incompatible.",
    },
    "err_uimsc_missing": {
        "zh": "未找到 uispritesmsc 图集——业力图标需 Downpour(More Slugcats) DLC。",
        "en": "uispritesmsc atlas not found — the karma icons need the Downpour (More Slugcats) DLC.",
    },
    "err_no_install": {
        "zh": "未能自动定位 Rain World 安装。\n请点下方按钮，手动选择你的 RainWorld 文件夹。",
        "en": "Could not automatically locate the Rain World installation.\nPlease click the button below to manually select your RainWorld folder.",
    },
}


def lang_name(code: str) -> str:
    return _STR["lang_name"][code]


def t(key: str, **kw) -> str:
    e = _STR.get(key)
    if e is None:
        return key
    s = e.get(LANG) or e.get("zh") or key
    return s.format(**kw) if kw else s
