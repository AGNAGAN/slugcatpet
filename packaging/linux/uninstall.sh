#!/usr/bin/env bash
# 卸载 SlugcatPet 的桌面入口、图标和 KWin 脚本；保留 ~/.slugcatpet 用户数据。
set -euo pipefail

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

if command -v uv >/dev/null 2>&1; then
    uv tool uninstall slugcatpet >/dev/null 2>&1 || true
fi

rm -f "$DATA_HOME/applications/org.slugcatpet.SlugcatPet.desktop"
rm -f "$DATA_HOME/icons/hicolor/scalable/apps/slugcatpet.svg"
rm -f "$CONFIG_HOME/autostart/org.slugcatpet.SlugcatPet.desktop"
rm -rf "$DATA_HOME/kwin/scripts/slugcatpet"

if command -v kwriteconfig6 >/dev/null 2>&1; then
    kwriteconfig6 --file kwinrc --group Plugins --key slugcatpetEnabled false || true
    if command -v qdbus6 >/dev/null 2>&1; then
        qdbus6 org.kde.KWin /Scripting org.kde.kwin.Scripting.unloadScript slugcatpet >/dev/null 2>&1 || true
        qdbus6 org.kde.KWin /KWin org.kde.KWin.reconfigure >/dev/null 2>&1 || true
    fi
else
    echo "未找到 kwriteconfig6；如已启用 KWin 集成，请在系统设置里关闭 slugcatpet 脚本。" >&2
    echo "kwriteconfig6 not found; disable the slugcatpet KWin script manually if needed." >&2
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
fi

echo "SlugcatPet 已卸载。用户数据 ~/.slugcatpet 保留。"
echo "SlugcatPet uninstalled. User data in ~/.slugcatpet was kept."
