import json,os, logging
from PyQt5.QtCore import QSettings, Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QCheckBox, QHBoxLayout, QPushButton
from utils import AppInfo

log = logging.getLogger('netconftool.data')

class AppData(object):
    def __init__(self) -> None:
        self._data = {}
        try:
            with open(os.path.join(self.settingDir(), 'setting.json'), 'r') as f:
                self._data = json.load(f)
        except Exception as ex:
            # self._data = json.loads(default_conf)
            pass
        self._sessions = self._data.get('session', [])
        self._history = self._data.get('history', [])
        self._command = self._data.get('favorite', {})
        self._ui_config = self._data.get('ui-config', {})

    def save(self):
        data={
            'session': self._sessions,
            'history': self._history,
            'favorite': self._command,
            'ui-config': self._ui_config
            }
        with open(os.path.join(self.settingDir(), 'setting.json'), 'w') as f:
            json.dump(data, f, indent=4)

    @staticmethod
    def settingDir() -> str:
        config_dir = AppInfo.settingDir()
        os.makedirs(config_dir, exist_ok=True)
        log.debug("Setting dir: %s", config_dir)
        return config_dir

    def addSession(self, session: dict):
        for item in self._sessions:
            if item == session:
                return
        self._sessions.append(session)

    def addSessions(self, ss: list):
        for s in ss:
            self.addSession(s)

    @property
    def sessions(self):
        return self._sessions

    @property
    def historys(self):
        return self._history

    def __set_command(self, cmds: dict):
        self._command = cmds

    def __set_ui_statusbar(self, state: bool):
        self._ui_config['satatus_bar'] = state

    def __set_ui_history(self, state: bool):
        self._ui_config['history'] = state

    def __set_ui_toolbar(self, state: bool):
        self._ui_config['tool_bar'] = state

    def __set_ui_language(self, lan: str):
        self._ui_config['language'] = lan

    def __set_ui_session(self, state: bool):
        self._ui_config['session'] = state

    def __set_ui_config(self, uiconfig: dict):
         for key in ['status_bar', 'history', 'tool_bar', 'language', 'session']:
            if not uiconfig.get(key, None) == None:
                self._ui_config[key] = uiconfig.get(key)

    ui_conf = property(fget=lambda self: self._ui_config, fset=__set_ui_config)

    ui_toolbar = property(fget=lambda self: self._ui_config.get('tool_bar', True),
                          fset=__set_ui_toolbar)

    ui_statusbar = property(fget=lambda self: self._ui_config.get('status_bar', True),
                            fset=__set_ui_statusbar)

    ui_history = property(fget=lambda self: self._ui_config.get('history', False),
                          fset=__set_ui_history)

    ui_language = property(fget=lambda self: self._ui_config.get('language', 'English'),
                           fset=__set_ui_language)

    ui_session = property(fget=lambda self: self._ui_config.get('session', False),
                          fset=__set_ui_session)

    commands = property(fget=lambda self: self._data.get('favorite', {'data':['name', 'xml', 'type']}),
                        fset = __set_command)
    @property
    def data(self) -> dict:
        return self._data

class SearchHistory(object):
    searchHistory=[]
    def __init__(self, need_load=True) -> None:
        if not need_load:
            return

        qsetting = QSettings(os.path.join(AppInfo.settingDir(), "setting.ini"), QSettings.IniFormat)
        qsetting.beginGroup('rundata')
         # auto check version
        history = qsetting.value('searchHistory')
        qsetting.endGroup()
        if history and not self.searchHistory:
            self.searchHistory.extend(history)
            log.debug("self.searchHistory: %s", self.searchHistory)

    def saveSearchHistory(self):
        qsetting = QSettings(os.path.join(AppInfo.settingDir(), "setting.ini"), QSettings.IniFormat)
        qsetting.beginGroup('rundata')
        qsetting.setValue('searchHistory', self.searchHistory)
        log.debug("save searchHistory: %s", self.searchHistory)
        qsetting.endGroup()

class RecentlySession(object):
    recentlySession=[]
    def __init__(self, need_load=True) -> None:
        if not need_load:
            return

        qsetting = QSettings(os.path.join(AppInfo.settingDir(), "setting.ini"), QSettings.IniFormat)
        qsetting.beginGroup('rundata')
        self.recentlySession = qsetting.value('recentlySession')
        qsetting.endGroup()
        log.debug("self.recentlySession: %s", self.recentlySession)

    @staticmethod
    def loadRecently() -> list:
        qsetting = QSettings(os.path.join(AppInfo.settingDir(), "setting.ini"), QSettings.IniFormat)
        qsetting.beginGroup('rundata')
        rs = qsetting.value('recentlySession', [])
        qsetting.endGroup()
        return rs if rs is not None else []

    @staticmethod
    def updateRecently(cfg:dict):
        qsetting = QSettings(os.path.join(AppInfo.settingDir(), "setting.ini"), QSettings.IniFormat)
        qsetting.beginGroup('rundata')
        recentlySession = qsetting.value('recentlySession', [])
        if recentlySession is None:
            recentlySession = []

        irs = {}
        irs['name'] = "%s@%s:%s"%(cfg.get('user',"NULL"),
                                  cfg.get('host') if cfg.get('type', 0) == 0 else "Dynamically",
                                  cfg.get('port'))
        irs['data'] = cfg
        for idx, rs in enumerate(recentlySession):
            if rs.get('name') == irs['name']:
                if idx == 0:
                    return
                del(recentlySession[idx])
        recentlySession.insert(0, irs)

        if len(recentlySession) > 20:
            del(recentlySession[20:])

        qsetting.setValue('recentlySession', recentlySession)
        qsetting.endGroup()
        log.debug("save searchHistory: %s", recentlySession)

    @staticmethod
    def clearRecently():
        qsetting = QSettings(os.path.join(AppInfo.settingDir(), "setting.ini"), QSettings.IniFormat)
        qsetting.beginGroup('rundata')
        qsetting.setValue('recentlySession', [])
        qsetting.endGroup()

class AppDataEx(QDialog):
    def __init__(self, title: str, config: dict, parent=None, flags=Qt.Dialog | Qt.WindowCloseButtonHint) -> None:
        super().__init__(parent, flags)
        self.setWindowTitle(title)
        self._type_list=[]
        vlayout = QVBoxLayout(self)
        vlayout.addWidget(QLabel("Select type:"))
        for item in config.keys():
            citem = QCheckBox(item, self)
            citem.setChecked(True)
            vlayout.addWidget(citem)
        vlayout.addStretch(1)
        vlayout.addSpacing(30)

        bt_ok = QPushButton("OK")
        bt_ok.setDefault(True)
        bt_ok.clicked.connect(self._ok)

        bt_cancel = QPushButton("Cancel")
        bt_cancel.clicked.connect(self.close)

        hlayout = QHBoxLayout()
        hlayout.addSpacing(100)
        hlayout.addStretch(1)
        hlayout.addWidget(bt_cancel)
        hlayout.addWidget(bt_ok)
        vlayout.addLayout(hlayout)

    def _ok(self):
        self._type_list.clear()
        list = self.findChildren(QCheckBox)
        for l in list:
            if l.isChecked() :
                self._type_list.append(l.text())
        self.accept()
        log.debug("Current select: %s", self._type_list)

    @property
    def selectedTypes(self):
        return self._type_list
