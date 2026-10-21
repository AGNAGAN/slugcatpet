#!/usr/bin/env bash
# SlugcatPet Linux 安装脚本：把 Python 包装进 uv tool 环境，并安装桌面入口/图标。
# KWin 集成默认不启用；启动应用后可在 设置 → Wayland / KWin 里显式勾选。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_DIR="${UV_TOOL_BIN_DIR:-$PREFIX/bin}"

if ! command -v uv >/dev/null 2>&1; then
    echo "未找到 uv。请先安装：https://docs.astral.sh/uv/getting-started/installation/" >&2
    echo "uv not found; install it from https://docs.astral.sh/uv/" >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "未找到 python3 / python3 not found" >&2
    exit 1
fi

echo "Installing SlugcatPet from: $ROOT"
UV_TOOL_BIN_DIR="$BIN_DIR" uv tool install --force --python 3.12 "$ROOT"

BIN="$BIN_DIR/slugcatpet"
if [ ! -x "$BIN" ]; then
    BIN="$(command -v slugcatpet || true)"
fi
if [ -z "$BIN" ] || [ ! -x "$BIN" ]; then
    echo "安装完成但找不到 slugcatpet 启动器。" >&2
    echo "Could not find the slugcatpet launcher after installation." >&2
    exit 1
fi

install -Dm644 "$ROOT/packaging/linux/slugcatpet.svg" \
    "$DATA_HOME/icons/hicolor/scalable/apps/slugcatpet.svg"

DESKTOP="$DATA_HOME/applications/org.slugcatpet.SlugcatPet.desktop"
TMP_DESKTOP="$(mktemp)"
trap 'rm -f "$TMP_DESKTOP"' EXIT
sed -e "s|^Exec=.*|Exec=\"$BIN\"|" \
    -e "s|^TryExec=.*|TryExec=$BIN|" \
    "$ROOT/packaging/linux/org.slugcatpet.SlugcatPet.desktop" >"$TMP_DESKTOP"
install -Dm644 "$TMP_DESKTOP" "$DESKTOP"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
fi

cat <<EOF

SlugcatPet 已安装到：$BIN
桌面入口：$DESKTOP

下一步 / Next:
  1. 从应用菜单启动 SlugcatPet，或运行：$BIN
  2. 首次启动选择 Rain World 安装目录。
  3. 如需 KWin 置顶/全屏检测/挡雨窗口/全局热键：
     设置 → Wayland / KWin → 勾选「登录后自动加载 KWin 脚本」。
     这会把脚本安装到 ~/.local/share/kwin/scripts/slugcatpet，并更新 kwinrc。
  4. 可选：在设置里打开「开机自动启动」。

KWin 脚本是显式可选的；不勾选也能在当前会话使用运行时脚本。
Uninstall with: $ROOT/packaging/linux/uninstall.sh
EOF
