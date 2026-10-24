"""蜥蜴桌宠的侧边栏：物品按钮由当前 app 的物品表决定，操作区只留退出。"""

from __future__ import annotations

from slugcatpet.i18n import t
from slugcatpet.ui.panels.tabbar import TabBar


class LizardSideBar(TabBar):
    def _build_actions(self, btn):
        btn(t("btn_quit_app"), True, self._quit)
