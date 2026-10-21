# SlugcatPet on Linux (KDE Plasma / Wayland)

This directory contains the Linux desktop entry, icon, and install scripts.
The app does **not** bundle Rain World assets; the first launch still imports
images and music from your own Rain World installation.

## Requirements

- KDE Plasma 6 with KWin 6 (tested on Plasma 6.8 / KWin 6.8)
- A Wayland session
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Rain World + Downpour installed locally

GNOME and Sway can run the app, but they do not provide the KWin bridge, so
topmost, fullscreen detection, rain shelters, global hotkeys, and cursor
position/writing are degraded or unavailable.

## Install

```bash
./packaging/linux/install.sh
```

The script installs the Python package into an isolated `uv tool` environment,
then places:

- `~/.local/share/applications/org.slugcatpet.SlugcatPet.desktop`
- `~/.local/share/icons/hicolor/scalable/apps/slugcatpet.svg`

Use `PREFIX=/some/prefix ./packaging/linux/install.sh` to change the launcher
prefix. `UV_TOOL_BIN_DIR` and the standard XDG variables are also respected.

Launch **SlugcatPet** from the application menu, or run `slugcatpet`.

## KWin integration

For the current session the app loads a runtime KWin script automatically.
To keep the bridge available after login, open:

**Settings → Wayland / KWin → Load KWin script at login**

This explicitly installs the rendered script to
`~/.local/share/kwin/scripts/slugcatpet/`, writes
`[Plugins] slugcatpetEnabled=true` in `kwinrc`, and calls
`org.kde.KWin.reconfigure`. The toggle is off by default; the app does not
modify `kwinrc` until you enable it.

If you use autostart, enable this too so the bridge is ready before the app
starts. The app still reloads the script with the current output geometry at
startup.

## Cursor writing

On Wayland the cursor grab uses a temporary fullscreen capture surface and
Qt's `wp_pointer_warp_v1` support. It is **best-effort**, not a system-level
pointer lock. Clicking left or right releases the grab; the release click is
consumed and does not click through. See
[`ai-docs/PHASE5_CURSOR_WRITE.md`](../../ai-docs/PHASE5_CURSOR_WRITE.md) for
the full architecture and known limits.

## Uninstall

```bash
./packaging/linux/uninstall.sh
```

This removes the launcher, desktop entry, icon, autostart entry, and KWin
script, and disables the KWin plugin. It does **not** delete `~/.slugcatpet`
(settings, imported assets, skins, and logs).

## Troubleshooting

### The KWin section says the script is not loaded

1. Make sure you are in a Plasma/Wayland session.
2. Enable **Load KWin script at login**, or press **Reload KWin script**.
3. Check that the DBus scripting interface exists:

   ```bash
   qdbus6 org.kde.KWin /Scripting org.kde.kwin.Scripting.isScriptLoaded slugcatpet
   ```

4. If the KWin script was disabled in System Settings, enable the
   `slugcatpet` script there as well.

### Cursor does not move while grabbed

- Cursor writing needs Qt 6.12+ and a compositor that advertises
  `wp_pointer_warp_v1`; XWayland is not supported.
- The app shows a busy cursor and hides the capture surface when the grab ends.
- If only readonly cursor following works, the app degrades to that mode; it
  does not fake a system-wide pointer lock.

### Input clicks go through / cats cannot be clicked

- The overlay uses one fullscreen surface with dynamic input regions. If
  another tool forces the window fullscreen or changes its mask, restart the
  app or reload the KWin script.
- On non-KWin compositors, geometry and input behavior are best-effort.

### Fullscreen video/game does not hide the pet

Fullscreen detection depends on the KWin bridge. Enable the integration and
make sure the fullscreen window is on the same output as the pet. Fullscreen
on a different output is intentionally ignored.

### Reset KWin integration

Turn the switch off, then on again. If the script was removed manually, the
next enable rewrites it. To remove everything, run `uninstall.sh`.
