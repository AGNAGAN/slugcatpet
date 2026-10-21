import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from slugcatpet.platform.appid import set_desktop_file_name
from slugcatpet.platform.wayland import kwin_install
from slugcatpet.window import PetWindow


def main():
    app = QApplication(sys.argv)
    set_desktop_file_name()
    app.setQuitOnLastWindowClosed(False)
    pet = PetWindow(params={"output": ""})
    pet.show()
    backend = pet.desktop_backend
    print("backend", type(backend).__name__, "service", getattr(backend, "_service_registered", None))

    def step1():
        print("supports", getattr(backend, "supports_geometry", None), getattr(backend, "supports_cursor", None))
        print("before", kwin_install.state())
        ok = backend.set_integration_enabled(True)
        print("enable", ok, kwin_install.state())

    def step2():
        print("after enable", kwin_install.state())
        print("loaded", __import__("subprocess").run(
            ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.isScriptLoaded", "slugcatpet"],
            capture_output=True, text=True).stdout.strip())
        ok = backend.set_integration_enabled(False)
        print("disable", ok, kwin_install.state())

    def step3():
        print("after disable", kwin_install.state())
        print("loaded", __import__("subprocess").run(
            ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.isScriptLoaded", "slugcatpet"],
            capture_output=True, text=True).stdout.strip())
        pet.close()
        app.quit()

    QTimer.singleShot(2500, step1)
    QTimer.singleShot(4500, step2)
    QTimer.singleShot(6500, step3)
    app.exec()


if __name__ == "__main__":
    main()
