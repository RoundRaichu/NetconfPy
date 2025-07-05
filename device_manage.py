from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import json

import logging
log = logging.getLogger('netconftool.devmanager')

class dmException(Exception):
    pass

# def ip_invalid_check(ipstr: str) -> bool:
#     try:
#         version = IPy.IP(ipstr).version()
#         if version == 4 or version == 6:
#             return True
#         else:
#             return False
#     except Exception as e:
#         return False

def SessionOptionsCheck(opt: dict):
    if type(opt) is not dict:
        return False, "Invalid session instance, please new one"
    log.debug("opt=%s", opt)

    if not opt['host'] :
        return False, str("Host is blank")
    elif not opt['port']:
        return False, "Port is blank"
    elif not opt['user']:
        return False, "Username is blank"
    elif not opt['passwd']:
        return False, "Password is blank"
    elif not opt['timeout']:
        return False, "Timeout is blank"

    # if ip_invalid_check(opt['host']) == False:
    #     return False, "Invalid IP address"

    return True, ""

class SessionOptionModel(QAbstractListModel):
    def __init__(self, session:list, parent=None) -> None:
        super().__init__(parent)
        self._sessions = session

    def rowCount(self, parent: QModelIndex = ...) -> int:
        return len(self._sessions)

    # def setData(self, index: QModelIndex, value: typing.Any, role: int = ...) -> bool:
    #     if role == Qt.ItemDataRole.DisplayRole:
    #         self._sessions[index.row()]['name'] = str(value)
    #     elif role == Qt.ItemDataRole.UserRole:
    #         self._sessions[index.row()] = dict(value)
    #     else:
    #         return False
    #     return True

    def data(self, index: QModelIndex, role = Qt.ItemDataRole.DisplayRole) -> QValidator:
        if not self.isValid(index):
            return
        if role == Qt.ItemDataRole.DisplayRole:
            return self._sessions[index.row()]['name']
        elif role == Qt.ItemDataRole.UserRole:
            return self._sessions[index.row()]
        else:
            return None

    def isValid(self, index: QModelIndex):
        if index.row() < 0 or index.row() > len(self._sessions)-1:
            return False
        return True

    def addSession(self, index: QModelIndex, option:dict):
        for item in self._sessions:
            if item == option:
                return
        self.beginInsertRows(index, index.row()+1, index.row()+1)
        self._sessions.insert(index.row()+1, option)
        self.endInsertRows()

    def updateSession(self, index: QModelIndex, option:dict):
        if self.isValid(index):
            self._sessions[index.row()] = option
            self.dataChanged.emit(index, index)

    def removeRow(self, row: int, parent: QModelIndex = ...) -> bool:
        if row < 0:
            return;
        self.beginRemoveRows(parent, row, row)
        self._sessions.remove(self._sessions[row])
        self.endRemoveRows()
        return True

class SessionOption(QWidget):
    class SessionType(int):
        NETCONF = 0
        NETCONF_CALLHOME = 1
        TYPE_MAX=2

    protol_type = ["NETCONF", "NETCONF Call Home"]
    port_tip = ['Port:', 'Listen on port:']
    def __init__(self, options:dict = None, parent=None, hideName:bool = False) -> None:
        super().__init__(parent)
        self._option = options

        self._type = QComboBox(self)
        # self._type.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self._type.addItems(["NETCONF", "NETCONF Call Home"])

        self._name = QLineEdit(self)
        self._host = QLineEdit(self)
        # ipValidator = QRegExpValidator(QRegExp('^((2[0-4]\d|25[0-5]|\d?\d|1\d{2})\.){3}(2[0-4]\d|25[0-5]|[01]?\d\d?)$'))
        # self._host.setValidator(ipValidator)
        self._host.setPlaceholderText("Hostname or IPv4/v6 address")

        self._port = QLineEdit(self)
        portValidator = QRegExpValidator(QRegExp(r'^([1-9](\d{0,3}))$|^([1-5]\d{4})$|^(6[0-4]\d{3})$|^(65[0-4]\d{2})$|^(655[0-2]\d)$|^(6553[0-5])$'))
        self._port.setValidator(portValidator)
        self._port.setPlaceholderText('1~65535')

        self._user = QLineEdit(self)

        self._passwd = QLineEdit(self)
        self._passwd.setEchoMode(QLineEdit.PasswordEchoOnEdit)

        self._timeout = QLineEdit(self)
        timeoutValidator = QRegExpValidator(QRegExp(r'^([1-9](\d{0,4}))$'))
        self._timeout.setValidator(timeoutValidator)
        self._timeout.setPlaceholderText('1~99999')
        self._portstr = QLabel(self.port_tip[0], self)
        if options and options.get('type', 0) == SessionOption.SessionType.NETCONF_CALLHOME:
            self._portstr.setText(self.port_tip[1])
        flayout = QFormLayout()
        if hideName is True and options and options.get('name', '') == '':
            self._name.hide()
        else:
            flayout.addRow("Session Name:", self._name)
        flayout.addRow("Protocol:", self._type)
        flayout.addRow("Host:", self._host)
        flayout.addRow(self._portstr, self._port)
        flayout.addRow("Username:       ", self._user)
        flayout.addRow("Password:", self._passwd)
        flayout.addRow("Timeout:", self._timeout)
        flayout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        flayout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self._cb_keepalive = QCheckBox("Send periodic queries (keep-alive)")
        self._cb_keepalive.setEnabled(False)
        self._cb_autoreconnect = QCheckBox("Auto-reconnect on connection loss")
        # self._cb_autoreconnect.setEnabled(False)

        vlayout = QVBoxLayout(self)
        vlayout.addLayout(flayout)
        vlayout.addWidget(self._cb_keepalive)
        vlayout.addWidget(self._cb_autoreconnect, 1)
        vlayout.addStretch(1)

        self._type.currentIndexChanged.connect(self._onProtocalTypeChanged)
        self.__updateView()

    @staticmethod
    def tryLoadOptionFromClipboard(defalut: dict = {}):
        option = defalut
        text = QApplication.clipboard().text()

        if len(text) > 1024:
            log.info("Clipboad contain more then 1KB text, skip to parse!")
            return option

        opt_arry = text.split('\n')
        log.debug("load clipboad info:%s", opt_arry)
        for opt in opt_arry:
            name_value = opt.split(':')
            if len(name_value) < 2:
                continue
            if name_value[0] in ['name', 'host', 'port', 'user', 'passwd', 'type']:
                option[name_value[0]] = name_value[1]

        return option

    @staticmethod
    def copyToClipboard(cfg: dict):
        text = '"NetConf Tool" Connection Info block\n'
        text += '---------------------------------------------\n'
        for key in cfg.keys():
            if key in ['name', 'host', 'port', 'user', 'passwd', 'type']:
                log.debug("%s:%s", key, cfg.get(key))
                text += "%s: %s\n"%(key, cfg.get(key))
        text += '---------------------------------------------\n'
        text += 'You can copy this text and open "NetConf Tool"\n'
        text += 'to connect the device directly.'
        QApplication.clipboard().setText(text)

    def _onProtocalTypeChanged(self, idx: int):
        self._portstr.setText(self.port_tip[idx])
        self._port.setText(['830', '4334'][idx])
        if idx == SessionOption.SessionType.NETCONF:
            self._cb_autoreconnect.setEnabled(True)
        else:
            self._cb_autoreconnect.setEnabled(False)
            self._cb_autoreconnect.setChecked(False)

    def setData(self, options:dict):
        if len(options['name']) == 0:
            options['name'] = options['host']
        self._option = options
        self.__updateView()

    def clearData(self):
        self._option['name'] = ""
        self._option['type'] = 0
        self._option['host'] = ""
        self._option['port'] = 830
        self._option['user'] = ""
        self._option['passwd'] = ""
        self._option['timeout'] = 60
        self._option['keep-alive'] = False
        self._option['auto-reconnect'] = False
        self.__updateView()

    @property
    def data(self) -> dict:
        if not self._option:
            log.info("self._option is null")
            return
        self._option['name'] = self._name.text().strip()
        self._option['type'] = self._type.currentIndex()
        self._option['host'] = self._host.text().strip()
        self._option['port'] = int(self._port.text() if self._port.text() else 830)
        self._option['user'] = self._user.text().strip()
        self._option['passwd'] = self._passwd.text().strip()
        self._option['timeout'] = int(self._timeout.text() if self._timeout.text() else 60)
        self._option['keep-alive'] = self._cb_keepalive.isChecked()
        self._option['auto-reconnect'] = self._cb_autoreconnect.isChecked()
        return self._option

    def __updateView(self):
        if not self._option:
            return
        self._name.setText(self._option['name'].strip())
        self._type.setCurrentIndex(int(self._option.get('type', 0)))
        self._host.setText(self._option['host'].strip())
        self._port.setText(str(self._option['port']).strip())
        self._user.setText(self._option['user'].strip())
        self._passwd.setText(self._option['passwd'].strip())
        self._timeout.setText(str(self._option['timeout']))
        self._cb_keepalive.setChecked(self._option.get('keep-alive') if self._option.get('keep-alive') else False)
        self._cb_autoreconnect.setChecked(self._option.get('auto-reconnect') if self._option.get('auto-reconnect') else False)

class SessionOptionDiag(QDialog):
    def __init__(self, options: dict, title: str, parent=None, showClear:bool=False, flags=Qt.Dialog | Qt.WindowCloseButtonHint):
        super().__init__(parent, flags)
        layout = QVBoxLayout()
        self._optwidget = SessionOption(options, self)
        layout.addWidget(self._optwidget)
        layout.addStretch(2)
        hlayout = QHBoxLayout()
        hlayout.addStretch()
        self._bt_cancel = QPushButton("Cancel", self)
        self._bt_cancel.clicked.connect(self.close)
        self._bt_ok = QPushButton("  OK  ", self)
        self._bt_ok.clicked.connect(self._ok)
        self._bt_ok.setDefault(True)
        if showClear is True:
            _bt_clear = QPushButton("Clear All", self)
            _bt_clear.clicked.connect(self._optwidget.clearData)
            hlayout.addWidget(_bt_clear)
            hlayout.addStretch(1)
        hlayout.addSpacing(130)
        hlayout.addWidget(self._bt_cancel)
        hlayout.addWidget(self._bt_ok)
        layout.addLayout(hlayout)
        self.setLayout(layout)
        self.setWindowIcon(QIcon(':/res/setting.png'))
        self.setWindowTitle(title)

    def _ok(self):
        opt = self._optwidget.data
        ret, msg = SessionOptionsCheck(opt)
        if ret == False:
            self.alert_warning(msg)
        else:
            if len(opt['name']) == 0:
                opt['name'] = opt['host']
            self._optwidget.setData(opt)
            self.accept()

    def alert_warning(self, text):
        QMessageBox.warning(self, "Warning", text, QMessageBox.Ok)

    @property
    def options(self):
        return self._optwidget.data

class QuickConnectDialg(QDialog):
    def __init__(self, options: dict, title: str, parent=None, flags=Qt.Dialog | Qt.WindowCloseButtonHint):
        super().__init__(parent, flags)
        layout = QVBoxLayout()
        self._optwidget = SessionOption(options, self, True)
        layout.addWidget(self._optwidget)
        layout.addStretch(2)
        layout.addSpacing(20)
        hlayout = QHBoxLayout()
        hlayout.addStretch()
        self._bt_cancel = QPushButton("Cancel", self)
        self._bt_cancel.clicked.connect(self.close)
        self._bt_connect = QPushButton("Connect", self)
        self._bt_connect.clicked.connect(self._ok)
        self._bt_connect.setDefault(True)
        self._cb_save_opt = QCheckBox("Save session", self)
        hlayout.addWidget(self._cb_save_opt)
        hlayout.addSpacing(50)
        hlayout.addStretch(1)
        hlayout.addWidget(self._bt_cancel)
        hlayout.addWidget(self._bt_connect)
        layout.addLayout(hlayout)
        self.setLayout(layout)
        self.setWindowIcon(QIcon(':/res/quick-connect.png'))
        self.setWindowTitle(title)

    def _ok(self):
        opt = self._optwidget.data
        ret, msg = SessionOptionsCheck(opt)
        if ret == False:
            self.alert_warning(msg)
        else:
            if len(opt['name']) == 0:
                opt['name'] = opt['host']
            self._optwidget.setData(opt)
            self.accept()

    def alert_warning(self, text):
        QMessageBox.warning(self, "Warning", text, QMessageBox.Ok)

    @property
    def options(self):
        return self._optwidget.data
    @property
    def isNeedSaveSession(self):
        return self._cb_save_opt.isChecked()

class DeviceConnectSignals(QObject):
    disconnected = pyqtSignal(str)
    connected = pyqtSignal(str)
    canceled = pyqtSignal()
    notification = pyqtSignal(str)

class DeviceManage(QDialog):
    def __init__(self, sessions: list, parent=None, flags=Qt.Dialog | Qt.WindowCloseButtonHint):
        super().__init__(parent, flags)
        self.signals = DeviceConnectSignals()
        self._sessions = sessions
        self.initUI()

    def __del__(self):
        log.debug("DeviceManage __del__")
        # self._ncc_manager.close()

    def initUI(self):
        self.setWindowTitle("Connect")
        self.setWindowIcon(QIcon(':/res/connected.png'))
        layout = QVBoxLayout(self)

        view = QListView(self)
        session_model = SessionOptionModel(self._sessions, self)
        view.setModel(session_model)
        view.setSelectionModel(QItemSelectionModel(session_model, self))
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        view.selectionModel().currentChanged.connect(self._onCurrentChanged)
        view.doubleClicked.connect(self._doConnect)

        act_copy = QAction("&Copy to Clipboard", self)
        act_copy.setShortcut(QKeySequence.Copy)
        act_copy.setShortcutContext(Qt.WidgetShortcut)
        act_copy.triggered.connect(self._onCopyAction)
        view.addAction(act_copy)

        self.act_copy = act_copy
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        view.customContextMenuRequested.connect(self._onCustomMenuRequest)

        list_group = QGroupBox("Device List", self)
        vlayout = QVBoxLayout()
        vlayout.addWidget(view)
        list_group.setLayout(vlayout)

        hlayout = QHBoxLayout()
        hlayout.addWidget(list_group, 2)

        log.debug("DeviceManage load session: %s", json.dumps(self._sessions, indent=4))
        info_group = QGroupBox("Information", self)
        info_group_layout = QVBoxLayout()
        self.sessionOption = SessionOption(None, self)

        info_group_layout.addWidget(self.sessionOption)
        info_group.setLayout(info_group_layout)

        hlayout.addWidget(info_group, 3)
        layout.addLayout(hlayout)

        bottom_layout = QHBoxLayout()
        self._bt_new = QPushButton("New", self)
        self._bt_new.clicked.connect(self._onCreateNewSession)
        self._bt_save = QPushButton("Save", self)
        self._bt_save.clicked.connect(self._save)
        self._bt_connect = QPushButton("Connect")
        self._bt_connect.clicked.connect(self._doConnect)
        self._bt_connect.setDefault(True)

        self._bt_cancel = QPushButton("Close")
        self._bt_cancel.clicked.connect(self.close)

        bottom_layout.addWidget(self._bt_new)
        bottom_layout.addStretch(1)
        bottom_layout.addWidget(self._bt_save)
        bottom_layout.addWidget(self._bt_cancel)
        bottom_layout.addWidget(self._bt_connect)
        layout.addLayout(bottom_layout)

        # self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        # self.show()
        # view.setCurrentIndex(session_model.index(0,0))
        self._session_view = view
        self.model = session_model

        if len(self._sessions):
            self.sessionOption.setData(self._sessions[0])
            view.setCurrentIndex(session_model.index(0,0))
        else:
            self.sessionOption.setEnabled(False)

    def _onCopyAction(self):
        index = self._session_view.currentIndex()
        if not index.isValid():
            return
        cfg = self.model.data(index, Qt.ItemDataRole.UserRole)
        SessionOption.copyToClipboard(cfg)

    def _onCustomMenuRequest(self, pos):
        menu = QMenu(self)
        act_new = QAction("New", menu)
        act_new.triggered.connect(self._onCreateNewSession)
        act_del = QAction("Delete", menu)
        act_del.triggered.connect(self._onDeleteSession)
        act_duplicate = QAction("Duplicate", menu)
        act_duplicate.triggered.connect(self._onDuplicateSession)
        menu.addAction(act_new)
        index = self._session_view.indexAt(pos)
        if index.isValid():
            menu.addAction(act_duplicate)
            menu.addAction(self.act_copy)
            menu.addSeparator()
            menu.addAction(act_del)

        menu.exec(QCursor.pos())
        del menu

    def _onCurrentChanged(self, index: QModelIndex):
        if index.isValid():
            log.debug("index is valid")
            self.sessionOption.setData(self.model.data(index, Qt.ItemDataRole.UserRole))
            self.sessionOption.setEnabled(True)
        else:
            log.debug("index is not valid")
            self.sessionOption.clearData()
            self.sessionOption.setEnabled(False)

    def _save(self):
        ret, msg = SessionOptionsCheck(self.sessionOption.data)
        if ret == False:
            self.alert_warning(msg)
        else:
            index = self._session_view.currentIndex()
            self.model.updateSession(index, self.sessionOption.data)

    def _onCreateNewSession(self):
        new = {"name": "New*", "host": "", "port": 830, "user": "", "passwd": "", "timeout": 60, "keep-alive": False, "auto-reconnect": False}
        opt = SessionOptionDiag(SessionOption.tryLoadOptionFromClipboard(new), "New Session", showClear=True)
        ret = opt.exec()
        if ret == QDialog.DialogCode.Accepted:
            log.debug("new options: %s, %d", opt.options, ret)
            index = self._session_view.currentIndex()
            self.model.addSession(index, new)
            if index.isValid():
                self._session_view.setCurrentIndex(index.sibling(index.row()+1, 0))
            else:
                self._session_view.setCurrentIndex(self.model.index(0, 0))

    def _onDeleteSession(self):
        index = self._session_view.currentIndex()
        self.model.removeRow(index.row(), index)
        sel_model = self._session_view.selectionModel()
        if self.model.rowCount() == 0:
            sel_model.clearCurrentIndex()
        elif index.row() == 0:
            sel_model.setCurrentIndex(index.sibling(0, 0), QItemSelectionModel.ClearAndSelect)
            self.sessionOption.setData(self.model.data(index.sibling(0, 0), Qt.ItemDataRole.UserRole))
        else :
            sel_model.setCurrentIndex(index.sibling(index.row()-1, 0), QItemSelectionModel.ClearAndSelect)

    def _onDuplicateSession(self):
        index = self._session_view.currentIndex()
        if index.row() < 0:
            return
        ss = self.model.data(index, Qt.ItemDataRole.UserRole)
        new = ss.copy()
        for i in range(1, 100, 1):
            dup = False
            tmpn="%s(%d)" % (new['name'], i)
            for s in self._sessions:
                if tmpn == s['name']:
                    dup = True;
                    break;
            if dup == False:
                break
        new['name'] = tmpn
        self.model.addSession(index, new)
        self._session_view.setCurrentIndex(index.sibling(index.row()+1, index.column()))

    @property
    def options(self):
        return self.sessionOption.data

    def _doConnect(self):
        index = self._session_view.currentIndex()
        log.debug('index: %d, %d', index.row(), index.column())
        if index.isValid():
            self.model.updateSession(index, self.sessionOption.data)
            self.accept()

    def alert_warning(self, text):
        QMessageBox.warning(self, "Warning", text, QMessageBox.Ok)

if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d: %(message)s',
                level=logging.DEBUG)
    app = QApplication([])
    widget = DeviceManage([])
    widget.show()
    app.exec()