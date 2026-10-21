import subprocess
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from slugcatpet.platform.appid import set_desktop_file_name
from slugcatpet.platform.wayland import kwin_install
from slugcatpet.window import PetWindow


def is_loaded():
    return subprocess.run(
        ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.isScriptLoaded", "slugcatpet-runtime"],
        capture_output=True, text=True).stdout.strip()


def main():
    app = QApplication(sys.argv)
    set_desktop_file_name()
    app.setQuitOnLastWindowClosed(False)
    pet = PetWindow(params={"output": ""})
    pet.show()
    backend = pet.desktop_backend

    def enable():
        print("enable", backend.set_integration_enabled(True), kwin_install.state(), "loaded", is_loaded())

    def disable():
        print("disable", backend.set_integration_enabled(False), kwin_install.state(), "loaded", is_loaded())

    def after_disable():
        print("after disable 2s loaded", is_loaded())
        print("manual reload", backend.reload(), "loaded", is_loaded())
        QTimer.singleShot(1000, after_reload)

    def after_reload():
        print("after manual reload 1s loaded", is_loaded())
        print("manual reload 2", backend.reload(), "loaded", is_loaded())
        QTimer.singleShot(1000, quit)

    def quit():
        print("final loaded", is_loaded())
        pet.close()
        app.quit()

    QTimer.singleShot(2000, enable)
    QTimer.singleShot(4000, disable)
    QTimer.singleShot(6000, after_disable)
    app.exec()


if __name__ == "__main__":
    main()
