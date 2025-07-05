import sys, os, logging, traceback
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from history import XmlHistory
from favorite import FavoriteDockWidget, AddToFavoriteDialog, FavoritesEditor
from session import NetconfSession, CallHomeDialog
from device_manage import *
from ncclient.xml_ import *
from about import About
from data import *
from utils import SingletonLogger
from updatecheck import VersionUpdate
import res_rc

slog = SingletonLogger()
log = logging.getLogger('netconftool')
app_data=AppData()

class DockWindowTitle(QWidget):
   def __init__(self, label="", parent=None, flags=Qt.WindowType.Widget) -> None:
      super().__init__(parent, flags)
      layout = QHBoxLayout()
      # layout.addSpacing(1)
      layout.addWidget(QLabel(label))
      # layout.addWidget(QLine(), 1)
      # layout.addStretch()
      if sys.platform == 'darwin':
         layout.setContentsMargins(1, 1, 1, 1)
      else:
         layout.setContentsMargins(5, 5, 5, 5)

      self.setLayout(layout)

class SessionListDockWidget(QWidget):
   def __init__(self, parent=None, flags=Qt.WindowType.Widget) -> None:
      super().__init__(parent, flags)

class MainWindow(QMainWindow):
   def __init__(self, appdata: AppData):
      super().__init__()
      self.appdata = appdata
      self.versionUpdate = VersionUpdate(self)
      self.versionUpdate.autoCheck()
      self.SessionOperCtlGroup = [] # 会话操作控制组
      self.sessionOpIndex = None
      self.favoritesEditor = None
      self.quickSessionOption = {"name": "", "host": "", "port": 830, "user": "", "passwd": "", "timeout": 60, "keep-alive": False, "auto-reconnect": False}
      self._createActions()
      self._initUI()

   def _createActions(self):
      action_xmledit = QAction(QIcon(':/res/add-to-favorites.png'), "&Favorites Editor", self)
      action_xmledit.triggered.connect(self._favoritesEdit)
      self.actXmlEdit = action_xmledit

      action_import = QAction("&Import Data...", self)
      action_import.triggered.connect(self._onImportAppData)
      self.actImportData = action_import

      action_export = QAction("&Export Data...", self)
      action_export.triggered.connect(self._onExportAppData)
      self.actExportData = action_export

      action_save = QAction("&Save Data Now", self)
      action_save.triggered.connect(self._onSaveAppData)
      # action_save.setShortcut(QKeySequence.Save)
      self.actSaveData = action_save

      action_exit = QAction("&Exit", self)
      action_exit.triggered.connect(self.close)
      self.actExit = action_exit

      action_connect = QAction(QIcon(':/res/connected.png'), "Connect...", self)
      action_connect.setStatusTip("Connect to new device")
      action_connect.setShortcut("Alt+c")
      action_connect.triggered.connect(self.openDevice)
      self.actConnect = action_connect

      action_qconnect = QAction(QIcon(':/res/quick-connect.png'), "Quick Connect...", self)
      action_qconnect.setStatusTip("Quick connect to new device")
      action_qconnect.setShortcut("Alt+q")
      action_qconnect.triggered.connect(self.openDeviceQuick)
      self.actQuickConnect = action_qconnect

      action_disconnect = QAction(QIcon(':/res/disconnected.png'), "Disconnect", self)
      action_disconnect.setStatusTip("Disconnect from device")
      action_disconnect.setEnabled(False)
      action_disconnect.triggered.connect(self.onDisconnectDevice)
      self.actDisconnect = action_disconnect

      action_disconnectAll = QAction("Disconnect All", self)
      action_disconnectAll.setStatusTip("Disconnect All device")
      action_disconnectAll.setEnabled(False)
      action_disconnectAll.triggered.connect(self.onDisconnectDeviceAll)
      self.actDisconnectAll = action_disconnectAll

      action_cloneSession = QAction(QIcon(':/res/clone-session.png'), "Clone Session", self)
      action_cloneSession.setStatusTip("Duplicate this session")
      action_cloneSession.setEnabled(False)
      action_cloneSession.triggered.connect(self.onCloneSession)
      self.actCloneSession = action_cloneSession

      action_copySessionInfo = QAction(QIcon(':/res/copy-to-clipboard.png'), "Copy Session Info", self)
      action_copySessionInfo.setStatusTip("Copy session information to clipboard")
      action_copySessionInfo.setEnabled(False)
      action_copySessionInfo.triggered.connect(self.onCopySessionOptions)
      self.actCopySessionInfo = action_copySessionInfo

      action_reconnect = QAction(QIcon(':/res/restart.png'), "Reconnect", self)
      action_reconnect.setStatusTip("Reconnect to device")
      action_reconnect.setEnabled(False)
      action_reconnect.triggered.connect(self.onReconnectDevice)
      self.actReconnect = action_reconnect

      action_reconnectall = QAction("Reconnect All", self)
      action_reconnectall.setStatusTip("Reconnect All device")
      action_reconnectall.setEnabled(False)
      action_reconnectall.triggered.connect(self.onReconnectDeviceAll)
      self.actReconnectAll = action_reconnectall

      act_closeAll = QAction("Close All Tabs", self)
      act_closeAll.triggered.connect(self.onCloseAllSessions)
      act_closeAll.setEnabled(False)
      self.actCloseAllSession = act_closeAll

      act_closeAllDisconnected = QAction("Close All Disconnected Tabs", self)
      act_closeAllDisconnected.triggered.connect(self.onClearAllDisconnectedSessions)
      act_closeAllDisconnected.setEnabled(False)
      self.actClearDisconnectedSession = act_closeAllDisconnected

      action_session_option = QAction(QIcon(':/res/setting.png'), "Session Options...", self)
      action_session_option.setStatusTip("Configure session options")
      action_session_option.triggered.connect(self.onModifySessionOptions)
      action_session_option.setEnabled(False)
      self.actSessionOptions = action_session_option

      action_copy_config = QAction(QIcon(':/res/copy.png'), "Copy Configuration...", self)
      action_copy_config.setStatusTip("Create or replace an entire configuration datastore")
      action_copy_config.setEnabled(False)
      action_copy_config.triggered.connect(lambda: self._session.currentWidget().onActCopyConfig())
      self.actCopyConfig = action_copy_config
      self.SessionOperCtlGroup.append(self.actCopyConfig)

      action_del_config = QAction(QIcon(':/res/no-register.png'), "Delete Configuration...", self)
      action_del_config.setStatusTip("Delete a configuration datastore")
      action_del_config.setEnabled(False)
      action_del_config.triggered.connect(lambda: self._session.currentWidget().onActDeleteConfig())
      self.actDeleteConfig = action_del_config
      self.SessionOperCtlGroup.append(self.actDeleteConfig)

      action_manag_lock = QAction(QIcon(':/res/lock.png'), "Manage Locks...", self)
      action_manag_lock.setStatusTip("Manage configuration datastore lock")
      action_manag_lock.setEnabled(False)
      action_manag_lock.triggered.connect(lambda: self._session.currentWidget().onActManageLocks())
      self.actManageLocks = action_manag_lock
      self.SessionOperCtlGroup.append(self.actManageLocks)

      action_validate_config = QAction(QIcon(':/res/validate.png'), "Validate Configuration...", self)
      action_validate_config.setStatusTip("Validate the contents of the specified configuration")
      action_validate_config.setEnabled(False)
      action_validate_config.triggered.connect(lambda: self._session.currentWidget().onActValidateConfig())
      # action need server capbility check
      action_validate_config.setData([':validate'])
      self.actValidateConfig = action_validate_config
      self.SessionOperCtlGroup.append(self.actValidateConfig)

      action_discardchanges = QAction(QIcon(':/res/discard-changes.png'), "Discard Changes", self)
      action_discardchanges.setStatusTip('Revert the candidate configuration to the currently running configuration')
      action_discardchanges.setEnabled(False)
      action_discardchanges.triggered.connect(lambda: self._session.currentWidget().onActDiscardChanges())
      action_discardchanges.setData([':candidate'])
      self.actDiscardChanges = action_discardchanges
      self.SessionOperCtlGroup.append(self.actDiscardChanges)

      action_commit = QAction(QIcon(':/res/commit.png'), "Commit", self)
      action_commit.setStatusTip("Commit the candidate configuration as the device's new current configuration")
      action_commit.setEnabled(False)
      action_commit.triggered.connect(lambda: self._session.currentWidget().onCommit())
      action_commit.setData([':candidate'])
      self.actCommit = action_commit
      self.SessionOperCtlGroup.append(self.actCommit)

      action_cancel_confirmed_commit = QAction(QIcon(':/res/cancel-commit.png'), "Cancel Confirmed Commit...", self)
      action_cancel_confirmed_commit.setStatusTip("Cancel an ongoing confirmed commit")
      action_cancel_confirmed_commit.setEnabled(False)
      action_cancel_confirmed_commit.triggered.connect(lambda: self._session.currentWidget().onActCancelConfirmedCommit())
      action_cancel_confirmed_commit.setData([':candidate', ':confirmed-commit'])
      self.actCancelConfirmedCommit = action_cancel_confirmed_commit
      self.SessionOperCtlGroup.append(self.actCancelConfirmedCommit)

      action_confirmed_commit = QAction(QIcon(':/res/confirm-commit.png'), "Confirmed Commit...", self)
      action_confirmed_commit.setStatusTip("Commit the candidate configuration as the device's new current configuration with confirm")
      action_confirmed_commit.setEnabled(False)
      action_confirmed_commit.triggered.connect(lambda: self._session.currentWidget().onActConfirmedCommit())
      action_confirmed_commit.setData([':candidate'])
      self.actConfirmedCommit = action_confirmed_commit
      self.SessionOperCtlGroup.append(self.actConfirmedCommit)

      action_capabilities = QAction(QIcon(':/res/capability.png'), "Capabilities", self)
      action_capabilities.setStatusTip("View server capabilities")
      action_capabilities.triggered.connect(self.onShowCap)
      action_capabilities.setEnabled(False)
      self.actCapabilities = action_capabilities
      self.SessionOperCtlGroup.append(self.actCapabilities)

      action_schema = QAction(QIcon(':/res/yinyang.png'), "Get Schema...", self)
      action_schema.setStatusTip("Load schema from server")
      action_schema.triggered.connect(self.onGetSchema)
      action_schema.setEnabled(False)
      self.actGetSchema = action_schema
      self.SessionOperCtlGroup.append(self.actGetSchema)

      action_xml_skeleton = QAction(QIcon(':/res/xml.png'), "Sample XML Skeleton", self)
      action_xml_skeleton.setStatusTip("View sample xml skeleton")
      action_xml_skeleton.setEnabled(False)
      self.actXmlSkeleton = action_xml_skeleton
      # self.SessionOperCtlGroup.append(self.actXmlSkeleton)

      action_session_manager = QAction(QIcon(':/res/session-manager.png'), "Session Manager", self)
      action_session_manager.setStatusTip("View and manager server session")
      action_session_manager.triggered.connect(lambda: self._session.currentWidget().onSessionManager())
      action_session_manager.setEnabled(False)
      self.actSessionManager = action_session_manager
      self.SessionOperCtlGroup.append(self.actSessionManager)

      action_toggle_statusbar = QAction("Status Bar", self)
      action_toggle_statusbar.setCheckable(True)
      action_toggle_statusbar.setChecked(self.appdata.ui_statusbar)
      action_toggle_statusbar.toggled.connect(self._onActionShowStatusBarToggled)
      self.actToggleStatusBar = action_toggle_statusbar

      self.actAbout = QAction("About", self)
      self.actAbout.triggered.connect(self._onAboutClicked)

      self.actReportIssue = QAction("Report Issue", self)
      self.actReportIssue.triggered.connect(self._onReportIssue)

      self.actHelp = QAction("Documentation", self)
      self.actHelp.triggered.connect(self._onHelpClicked)

      action_checkupdate = QAction("Check for Updates...", self)
      action_checkupdate.triggered.connect(self._onCheckforUpdates)
      self.actCheckUpdate = action_checkupdate

      action_clear_recently = QAction("Clear Recently...", self)
      action_clear_recently.triggered.connect(self._onClearRecently)
      self.actClearRecently = action_clear_recently

      recently_session_group = QActionGroup(self)
      recently_session_group.triggered.connect(self._recentlySessionListTriggered)
      self._recentlyListActionGroup = recently_session_group

   def _initMenu(self):
      # File menu
      file_menu = self.menuBar().addMenu("&File")
      file_menu.aboutToShow.connect(self._onFileMenuShow)
      file_menu.addActions([self.actConnect,
                            self.actQuickConnect])

      recent_menu = QMenu("Recent", file_menu)
      recent_menu.aboutToShow.connect(self._onRecentMenuShow)
      self._recentlyMenu = recent_menu
      file_menu.addMenu(recent_menu)

      file_menu.addSeparator()
      file_menu.addActions([self.actReconnect,
                            self.actReconnectAll,
                            self.actDisconnect,
                            self.actDisconnectAll])
      file_menu.addSeparator()
      file_menu.addActions([self.actCloneSession])
      file_menu.addSeparator()
      file_menu.addAction(self.actXmlEdit)
      file_menu.addSeparator()
      file_menu.addActions([self.actImportData, self.actExportData, self.actSaveData])

      debug_menu = QMenu("Debug", self)
      open_logdir = QAction("Open Log Directory", debug_menu)
      open_logdir.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(AppInfo.logdir())))
      debug_menu.addAction(open_logdir)

      log_level_group = QActionGroup(self)
      log_level_group.setExclusive(True)
      for level in slog.LEVELS.keys():
         act = QAction(level, self)
         act.setCheckable(True)
         if level == 'INFO':
            act.setChecked(True)
         act.setData(slog.LEVELS.get(level))
         log_level_group.addAction(act)
      log_level_group.triggered.connect(lambda act: slog.setLevel(act.data()))
      log_level_menu = QMenu("Set Level", debug_menu)
      log_level_menu.addActions(log_level_group.actions())
      debug_menu.addMenu(log_level_menu)

      file_menu.addSeparator()
      file_menu.addAction(self.actExit)

      # View menu
      view_menu = self.menuBar().addMenu("&View")
      view_menu.addAction(self._dw_favorite.toggleViewAction())
      view_menu.addAction(self._dw_history.toggleViewAction())
      view_menu.addAction(self.toolBar.toggleViewAction())
      view_menu.addAction(self.actToggleStatusBar)

      lan_group = QActionGroup(self)
      lan_group.setExclusive(True)
      lan_group.triggered.connect(self._languageChange)
      lan_list = ['中文', 'English']
      for lan in lan_list:
         act = QAction(lan, self)
         act.setCheckable(True)
         if self.appdata.ui_language == lan:
            act.setChecked(True)
         act.setData(lan)
         lan_group.addAction(act)
      language_menu = QMenu("Language", view_menu)
      language_menu.addActions(lan_group.actions())
      view_menu.addSeparator()
      view_menu.addMenu(language_menu)

      # Options menu
      options_menu = self.menuBar().addMenu("&Options")
      options_menu.addAction(self.actCopySessionInfo)
      options_menu.addAction(self.actSessionOptions)

      # Tools menu
      tools_menu = self.menuBar().addMenu("&Tools")
      tools_menu.addActions([self.actXmlSkeleton,
                             self.actCopyConfig,
                             self.actDeleteConfig,
                             self.actManageLocks,
                             self.actValidateConfig])
      tools_menu.addSeparator()
      tools_menu.addActions([self.actDiscardChanges,
                             self.actCommit,
                             self.actCancelConfirmedCommit,
                             self.actConfirmedCommit])
      tools_menu.addSeparator()
      tools_menu.addActions([self.actCapabilities,
                             self.actGetSchema,
                             self.actSessionManager])

      # Window menu
      window_menu = self.menuBar().addMenu("&Window")
      window_menu.aboutToShow.connect(self._onWindowMenuShow)
      tipAction = QAction("Single Tab Group", self)
      tipAction.setEnabled(False)
      window_menu.addAction(self.actClearDisconnectedSession)
      window_menu.addAction(self.actCloseAllSession)
      window_menu.addSeparator()
      window_menu.addAction(tipAction)
      window_menu.addSeparator()
      self._SessionWindowMenu = window_menu

      tab_act_group = QActionGroup(self)
      tab_act_group.setExclusive(True)
      tab_act_group.triggered.connect(self._sessionListTriggered)
      self._sessionListActionGroup = tab_act_group

      # help menu
      help_menu = self.menuBar().addMenu("&Help")
      help_menu.addAction(self.actHelp)
      help_menu.addSeparator()
      help_menu.addMenu(debug_menu)
      help_menu.addAction(self.actReportIssue)
      help_menu.addSeparator()
      help_menu.addAction(self.actCheckUpdate)
      help_menu.addSeparator()
      help_menu.addAction(self.actAbout)

   def _initToolbar(self):
      toolbar = QToolBar("Toolbar", self)
      toolbar.setObjectName("Toolbar")
      toolbar.setMovable(False)
      toolbar.setVisible(self.appdata.ui_toolbar)
      toolbar.toggleViewAction().triggered.connect(self._onActionShowToolBarToggled)

      toolbar.addAction(self.actConnect)
      toolbar.addAction(self.actQuickConnect)
      toolbar.addSeparator()
      toolbar.addAction(self.actReconnect)
      toolbar.addAction(self.actDisconnect)
      toolbar.addAction(self.actSessionOptions)
      toolbar.addSeparator()
      toolbar.addActions([self.actXmlSkeleton,
                          self.actCopyConfig,
                          self.actDeleteConfig,
                          self.actManageLocks,
                          self.actValidateConfig])

      toolbar.addSeparator()
      toolbar.addActions([self.actDiscardChanges,
                          self.actCommit,
                          self.actCancelConfirmedCommit,
                          self.actConfirmedCommit])
      toolbar.addSeparator()
      toolbar.addActions([self.actCapabilities, self.actGetSchema, self.actSessionManager])

      if sys.platform == 'darwin':
         toolbar.setIconSize(QSize(22, 22))

      self.addToolBar(toolbar)
      self.toolBar = toolbar
      self.setToolButtonStyle(Qt.ToolButtonIconOnly)

   def _initUI(self):
      self._session = QTabWidget(self)
      self._session.setDocumentMode(True if sys.platform == 'darwin' else False)
      self._session.setTabsClosable(True)
      self._session.setMovable(True)
      self._session.tabCloseRequested.connect(self._onCloseTab)
      self._session.currentChanged.connect(self.updateUiInformation)
      if not sys.platform == 'darwin':
         self._session.tabBar().setStyleSheet("QTabBar::close-button{border-image: url(':/res/close.png');}QTabBar::close-button:hover{background: lightgray;}")

      # self._session.tabBar().addActions([self.actDisconnect, self.actReconnect, self.actSessionOptions])
      self._session.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
      self._session.tabBar().customContextMenuRequested.connect(self._onCustomMenuRequest)
      self._session.tabBar().setAutoHide(True)
      # self._session.tabBar().setDocumentMode(True)

      self._session.addAction(self.actConnect)
      self._session.addAction(self.actQuickConnect)
      #self._session.addAction(self.actSessionOptions)
      # self._session.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
      self.setCentralWidget(self._session)

      self._dw_favorite = QDockWidget("Favorites", self)
      self._dw_favorite.setObjectName("Favorites")
      self._dw_favorite.setMinimumSize(150, 100)
      self._dw_favorite.setTitleBarWidget(DockWindowTitle("Favorites", self))
      self._dw_favorite.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
      self._dw_favorite.toggleViewAction().triggered.connect(self._onActionShowDockToggled)
      self._dw_favorite.setVisible(self.appdata.ui_session)

      self._dw_history = QDockWidget("Command History", self)
      self._dw_history.setObjectName("History")
      self._dw_history.setTitleBarWidget(DockWindowTitle("Command History", self))
      self._dw_history.toggleViewAction().triggered.connect(self._onActionHistoryToggled)
      self._dw_history.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
      self._dw_history.setVisible(self.appdata.ui_history)

      self._xml_history = XmlHistory(app_data.historys, self)
      self._xml_history.signals.reSentRequest.connect(self.onResendXML)
      self._xml_history.signals.addToFavorite.connect(self.onAddFavorite)
      self._dw_history.setWidget(self._xml_history)

      self._xml_favorite = FavoriteDockWidget(app_data.commands, self)
      self._xml_favorite.signals.reSentRequest.connect(self.onResendXML)
      self._xml_favorite.signals.activeItemChanged.connect(self._xml_history.setPreview)
      self._xml_favorite.signals.executeRequest.connect(lambda cxmls:  self.onExecuteXmlRequset(cxmls, False))
      self._xml_favorite.signals.executeAllRequest.connect(lambda cxmls:  self.onExecuteXmlRequset(cxmls, True))
      self._xml_favorite.signals.openFavoriteEditor.connect(self._favoritesEdit)

      self._dw_favorite.setWidget(self._xml_favorite)

      self.addDockWidget(Qt.RightDockWidgetArea, self._dw_favorite)
      self.addDockWidget(Qt.RightDockWidgetArea, self._dw_history)

      status_bar = QStatusBar(self)
      status_bar.setStyleSheet("QStatusBar::item{border:0px}")
      status_bar.setHidden(not self.appdata.ui_statusbar)
      self._status_connectinfo = QLabel("Ready")
      status_bar.addWidget(self._status_connectinfo)
      self.setStatusBar(status_bar)

      self._initToolbar()
      self._initMenu()

      self.setUnifiedTitleAndToolBarOnMac(True)
      self.setDockNestingEnabled(True)

   def _sessionListTriggered(self, act: QAction):
      idx = act.data();
      log.debug("_sessionListTriggered: idx=%d", idx)
      self._session.setCurrentIndex(idx)

   def _onFileMenuShow(self):
      log.debug("_onFileMenuShow")
      sessionTab = self._session
      have_disconnect_session = False
      have_connected_session = False

      for idx in range(sessionTab.count()):
         w = sessionTab.widget(idx)
         if w.connected:
            have_connected_session = True
         else:
            have_disconnect_session = True

      self.actReconnectAll.setEnabled(have_disconnect_session)
      self.actDisconnectAll.setEnabled(have_connected_session)

   def _onRecentMenuShow(self):
      log.debug("_onRecentMenuShow")
      actList = self._recentlyListActionGroup
      for act in actList.actions():
         actList.removeAction(act)
         del act

      rs = RecentlySession.loadRecently()
      self.actClearRecently.setEnabled(True if len(rs) > 0 else False)
      for t in rs:
         act = QAction(t.get('name'), actList)
         act.setData(t.get('data'))
         actList.addAction(act)
      self._recentlyMenu.clear()
      self._recentlyMenu.addActions(actList.actions())
      self._recentlyMenu.addSeparator()
      self._recentlyMenu.addAction(self.actClearRecently)

   def _addRecentlySession(self, cfg:dict):
      RecentlySession.updateRecently(cfg)

   def _onClearRecently(self):
      result = QMessageBox.warning(self, "Clear Recently", "Do you want to clear all recently session?\n\nThis action is irreversible!",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
      if result != QMessageBox.Yes:
         return
      RecentlySession.clearRecently()

   def _recentlySessionListTriggered(self, a0 = 0):
      log.info("_recentlySessionListTriggered a0=%s", a0.text())
      self._createSession(a0.data())

   def _onWindowMenuShow(self):
      log.debug("_onWindowMenuShow")
      sessionTab = self._session
      tab_act_group = self._sessionListActionGroup

      # clear first
      for a in tab_act_group.actions():
         tab_act_group.removeAction(a)

      self.actClearDisconnectedSession.setEnabled(False)
      if sessionTab.count() <= 0:
         self.actCloseAllSession.setEnabled(False)
         return

      self.actCloseAllSession.setEnabled(True)
      for idx in range(sessionTab.count()):
         w = sessionTab.widget(idx)
         if not w.connected:
            self.actClearDisconnectedSession.setEnabled(True)
            break

      curIdx = sessionTab.currentIndex()

      for idx in range(sessionTab.count()):
         w = sessionTab.widget(idx)
         act = QAction("%d "%idx + sessionTab.tabText(idx) + " - %s"%('Connected' if w.connected else 'Disconnected'), self)

         act.setData(idx)
         act.setCheckable(True)
         act.setChecked(True if idx == curIdx else False)
         tab_act_group.addAction(act)

      self._SessionWindowMenu.addActions(tab_act_group.actions())

   class SessionTabRenameDlg(QDialog):
      def __init__(self, preText="", parent=None, flags=Qt.Dialog | Qt.WindowCloseButtonHint) -> None:
         super().__init__(parent, flags)
         self.setWindowTitle("Rename Label")
         mainlayout = QVBoxLayout(self)
         mainlayout.addWidget(QLabel("Please enter a new label for this tab."))
         self.input = QLineEdit(self)
         self.input.setText(preText)
         self.input.selectAll()
         mainlayout.addWidget(self.input)

         bt_cancel = QPushButton("Cancel", self)
         bt_cancel.clicked.connect(self.close)

         bt_ok = QPushButton("OK", self)
         bt_ok.setDefault(True)
         bt_ok.clicked.connect(self._onOk)

         hlayout = QHBoxLayout()
         hlayout.addStretch(1)
         hlayout.addWidget(bt_cancel)
         hlayout.addWidget(bt_ok)

         mainlayout.addLayout(hlayout)
         mainlayout.setSizeConstraint(QLayout.SetFixedSize)

      def _onOk(self):
         self.accept()

      @property
      def name(self):
         return self.input.text()

   def _renameSessionTabName(self, index=None):
      if self.sessionOpIndex != None:
         idx = self.sessionOpIndex
      else:
         idx = self._session.currentIndex()

      cur_name =self._session.tabText(idx)
      dlg = self.SessionTabRenameDlg(cur_name, self)
      if dlg.exec() != QDialog.DialogCode.Accepted or len(dlg.name) == 0:
         return
      self._session.setTabText(idx, dlg.name)
      self._updateWindowTitle()

   def _resetSessionTabName(self):
      if self.sessionOpIndex != None:
         idx = self.sessionOpIndex
      else:
         idx = self._session.currentIndex()
      w = self._session.widget(idx)
      new_name = self.genSessionTableName(w.sessionName)
      w.setDisplayName(new_name)
      self._session.setTabText(idx, new_name)
      self._updateWindowTitle()

   def _onCustomMenuRequest(self, pos: QPoint):
      menu = QMenu(self)
      index = self._session.tabBar().tabAt(pos)

      act_renameTabname = QAction("Rename", menu)
      act_renameTabname.triggered.connect(self._renameSessionTabName)

      act_resetTabname = QAction("Reset Name", menu)
      act_resetTabname.triggered.connect(self._resetSessionTabName)

      action_disconnect = QAction(QIcon(':/res/disconnected.png'), "Disconnect", menu)
      action_disconnect.triggered.connect(self.onDisconnectDevice)

      action_reconnect = QAction(QIcon(':/res/restart.png'), "Reconnect", menu)
      action_reconnect.triggered.connect(self.onReconnectDevice)

      act_close = QAction("Close", menu)
      act_close.triggered.connect(self.onClose)

      act_closeAllDisconnected = QAction("Close All Disconnected Tabs", menu)
      act_closeAllDisconnected.setEnabled(False)
      act_closeAllDisconnected.triggered.connect(self.onClearAllDisconnectedSessions)

      act_closeOther = QAction("Close Other Tabs", menu)
      act_closeOther.triggered.connect(self.onCloseOtherSession)

      act_closeToRight = QAction("Close Tabs to the Right", menu)
      act_closeToRight.triggered.connect(self.onCloseToRight)

      act_closeAll = QAction("Close All Tabs", menu)
      act_closeAll.triggered.connect(self.onCloseAllSessions)

      action_cloneSession = QAction(QIcon(':/res/clone-session.png'), "Clone Session", menu)
      action_cloneSession.triggered.connect(self.onCloneSession)

      action_session_option = QAction(QIcon(':/res/setting.png'), "Session Options...", menu)
      action_session_option.triggered.connect(self.onModifySessionOptions)

      action_copySessionInfo = QAction(QIcon(':/res/copy-to-clipboard.png'), "Copy Session Info", menu)
      action_copySessionInfo.triggered.connect(self.onCopySessionOptions)

      w = self._session.widget(index)
      if w.connected:
         action_reconnect.setEnabled(False)
         action_disconnect.setEnabled(True)
         action_cloneSession.setEnabled(True)
      else:
         action_reconnect.setEnabled(True)
         action_disconnect.setEnabled(False)
         action_cloneSession.setEnabled(False)

      if self._session.tabText(index) == w.displayName:
         act_resetTabname.setEnabled(False)
      else:
         act_resetTabname.setEnabled(True)

      tab_cnt = self._session.count()
      act_closeToRight.setEnabled(True if index + 1 < tab_cnt else False)
      act_closeOther.setEnabled(True if tab_cnt > 1 else False)

      for idx in range(tab_cnt):
         w = self._session.widget(idx)
         if not w.connected:
            act_closeAllDisconnected.setEnabled(True)
            break

      menu.addActions([act_renameTabname,
                       act_resetTabname,
                       action_reconnect,
                       action_disconnect])
      menu.addSeparator()
      menu.addActions([act_close,
                       act_closeAllDisconnected,
                       act_closeOther,
                       act_closeToRight,
                       act_closeAll])
      menu.addSeparator()
      menu.addAction(action_cloneSession)
      menu.addSeparator()
      menu.addAction(action_copySessionInfo)
      menu.addAction(action_session_option)

      self.sessionOpIndex = index
      menu.exec(QCursor.pos())
      self.sessionOpIndex = None

   def onShowCap(self):
      sw = self._session.currentWidget()
      if sw and sw.connected:
         sw.onShowCap()

   def onGetSchema(self):
      sw = self._session.currentWidget()
      if sw and sw.connected:
         sw.onGetSchema()

   def _languageChange(self, act:QAction):
      log.debug("Languate seleted: %s", act.data())
      self.appdata.ui_language = act.data()

   def _updateStatusBar(self):
      w = self._session.currentWidget()
      if w and w.connected:
         self._status_connectinfo.setText("Connected to %s Session-ID: %s" %(w.connectInfoStr, w.sesson_id))
      else:
         self._status_connectinfo.setText("Ready")

   def _updateWindowTitle(self):
      if self._session.count() :
         nct = self._session.currentWidget()
         if nct.connected:
             st = "Connected"
         else:
             st = "Disconnected"
         tabtext = self._session.tabText(self._session.indexOf(nct))
         self.setWindowTitle("NetConf Tool - %s - %s" % (tabtext, st))
      else:
         self.setWindowTitle("NetConf Tool")

   def _updateWidgetStatus(self):
      w = self._session.currentWidget()
      if w :
         operable = w.sessionOperable
         """根据能力值显示可操作状态"""
         for act in self.SessionOperCtlGroup:
            sta = operable
            if operable is True and act.data() is not None:
               for cap in act.data():
                  if not w.serverHaveCapability(cap):
                     sta = False
                     break
            # log.debug("sta=%s, operable=%s", sta, operable)
            act.setEnabled(sta)

         if w.connected:
            self.actReconnect.setEnabled(False)
            self.actDisconnect.setEnabled(True)
            self.actCloneSession.setEnabled(True)
         else:
            self.actReconnect.setEnabled(True)
            self.actDisconnect.setEnabled(False)
            self.actCloneSession.setEnabled(False)
         self.actSessionOptions.setEnabled(True)
         self.actCopySessionInfo.setEnabled(True)
      else:
         self.actDisconnect.setEnabled(False)
         self.actCloneSession.setEnabled(False)
         self.actReconnect.setEnabled(False)
         self.actSessionOptions.setEnabled(False)
         self.actCopySessionInfo.setEnabled(False)
         for act in self.SessionOperCtlGroup:
            act.setEnabled(False)

   def _updateAllTabBarInfo(self):
      for id in range(self._session.count()):
         sw = self._session.widget(id)
         if sw.connected:
            if not sys.platform == 'darwin':
               self._session.setTabIcon(id, QIcon(':/res/ok.png'))
         else:
            if not sys.platform == 'darwin':
               self._session.setTabIcon(id, QIcon(':/res/unavailable.png'))

   def updateUiInformation(self):
      self._updateStatusBar()
      self._updateWindowTitle()
      self._updateWidgetStatus()
      self._updateAllTabBarInfo()

   def genSessionTableName(self, preName: str):
      exist_name = []
      for id in range(self._session.count()):
            exist_name.append(self._session.tabText(id))

      if not preName in exist_name:
         return preName

      for i in range(1, 100, 1):
         tmpn="%s(%d)" % (preName, i)
         if not tmpn in exist_name:
            return tmpn

      log.info("seq overflow. use max")
      return tmpn

   def _createSession(self, cfg: dict):
      type = cfg.get('type', 0)
      if type == SessionOption.SessionType.NETCONF_CALLHOME:
         dlg = CallHomeDialog(cfg, self)
         if dlg.exec() != QDialog.DialogCode.Accepted:
            return
      log.debug("Open session Options: %s", cfg)
      nct = NetconfSession(cfg, self)
      nct.signals.connectionStatusChange.connect(self.updateUiInformation)
      nct.signals.sendXmlNotify.connect(self.xmlHistoryAdd)
      nct.signals.sessionOperableChanged.connect(self._updateWidgetStatus)
      displayName = self.genSessionTableName(nct.sessionName)
      nct.setDisplayName(displayName)
      self._session.addTab(nct, displayName)
      self._session.setCurrentWidget(nct)
      if not sys.platform == 'darwin':
         self._session.setTabIcon(self._session.currentIndex(), QIcon(':/res/unavailable.png'))
      self._session.setTabToolTip(self._session.currentIndex(), displayName)
      if type == SessionOption.SessionType.NETCONF_CALLHOME:
         nct.setManager(dlg.worker.mgr, dlg.worker.raddr)
      nct.connect()
      self._addRecentlySession(cfg)

   def openDevice(self):
      diag = DeviceManage(app_data.sessions, self)
      if diag.exec() == QDialog.DialogCode.Accepted:
         self._createSession(diag.options)

   def openDeviceQuick(self):
      option = self.quickSessionOption.copy()
      option['name'] = ''
      opt = QuickConnectDialg(SessionOption.tryLoadOptionFromClipboard(option), "Quick Connect", self)
      ret = opt.exec()
      if ret == QDialog.DialogCode.Accepted:
         option = opt.options
         log.debug("Quick Connect options: %s, %d", option, ret)
         if option.get('name', '') == '':
            option['name'] = option.get("host")
         self.quickSessionOption = option
         self._createSession(option)
         if opt.isNeedSaveSession == True:
            app_data.addSession(option)

   def center(self):
      screen = QDesktopWidget().screenGeometry()
      size = self.geometry()
      self.move(int((screen.width() - size.width()) / 2),  int((screen.height() - size.height()) / 2))

   def onDisconnectDevice(self, index = None):
      if self.sessionOpIndex != None:
         w = self._session.widget(self.sessionOpIndex)
      else:
         w = self._session.currentWidget()

      if w and w.connected:
         w.disconnect()

   def onDisconnectDeviceAll(self):
      sessionTab = self._session
      for idx in range(sessionTab.count()):
         w = sessionTab.widget(idx)
         if w.connected:
            w.disconnect()

   def onReconnectDevice(self, index = None):
      if self.sessionOpIndex != None:
         w = self._session.widget(self.sessionOpIndex)
      else:
         w = self._session.currentWidget()

      if w and not w.connected:
         if w.options.get('type', 0) == SessionOption.SessionType.NETCONF_CALLHOME:
            return QMessageBox.warning(self, "Reconnect warning", "Call Home session is unable to reconnect.")
         w.connect()

   def onReconnectDeviceAll(self):
      sessionTab = self._session
      for idx in range(sessionTab.count()):
         w = sessionTab.widget(idx)
         if w and not w.connected:
            w.connect()

   def onCloneSession(self, index=None):
      if self.sessionOpIndex != None:
         w = self._session.widget(self.sessionOpIndex)
      else:
         w = self._session.currentWidget()
      self._createSession(w.options)

   def _closeSession(self, sw:NetconfSession, no_confirm:bool = False):
      if sw is None:
         return
      idx = self._session.indexOf(sw)
      if sw and sw.connected and no_confirm is False:
         result = QMessageBox.question(self, "Close", "Do you wish to disconnect from %s?\n%s" % (self._session.tabText(idx), sw.connectInfoStr),
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
         if result != QMessageBox.Yes:
            return
      log.debug("close:" + sw.connectInfoStr)
      self._session.removeTab(idx)
      sw.close()

   def onClose(self):
      if self.sessionOpIndex != None:
         w = self._session.widget(self.sessionOpIndex)
      else:
         w = self._session.currentWidget()
      self._closeSession(w)

   def onCloseOtherSession(self):
      if self.sessionOpIndex != None:
         exp = self._session.widget(self.sessionOpIndex)
      else:
         exp = self._session.currentWidget()
      wa = []
      for idx in range(self._session.count()):
         w = self._session.widget(idx)
         '''需要保留的会话'''
         if exp and exp is w:
            continue
         wa.append(w)
      for w in wa:
         self._closeSession(w)

   def onCloseToRight(self):
      if self.sessionOpIndex != None:
         exp = self._session.widget(self.sessionOpIndex)
      else:
         exp = self._session.currentWidget()

      cur_idx = self._session.indexOf(exp)
      wa = []
      for idx in range(cur_idx+1, self._session.count(), 1):
         wa.append(self._session.widget(idx))

      for w in wa:
         self._closeSession(w)

   def _closeAllSessions(self, disconnected_only = False):
      ws = []
      sessionTab = self._session
      for idx in range(sessionTab.count()):
         w = sessionTab.widget(idx)
         if w.connected and disconnected_only is True:
            continue
         ws.append(w)

      if disconnected_only is not True:
         result = QMessageBox.warning(self, "Close All Sessions", "Do you wish to disconnect and close all sessions?",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
         if result != QMessageBox.Yes:
            return

      for w in ws:
         self._closeSession(w, True)

   """关闭的所有会话"""
   def onCloseAllSessions(self):
      self._closeAllSessions()

   """清理已关闭的会话"""
   def onClearAllDisconnectedSessions(self):
      self._closeAllSessions(True)

   def _onCloseTab(self, index: int):
      sw = self._session.widget(index)
      self._closeSession(sw)

   def xmlHistoryAdd(self, xml: str):
      self._xml_history.addHistory(xml)

   def onResendXML(self, cxml):
      w = self._session.currentWidget()
      if w and len(cxml):
         w.setCommandXML(cxml)

   def onExecuteXmlRequset(self, cxmls: list, to_all: False):
      if not len(cxmls) or self._session.count() == 0:
         return
      sessions=[]
      if to_all:
         for id in range(self._session.count()):
            sw = self._session.widget(id)
            if sw.connected:
               sessions.append(self._session.widget(id))
      else:
         sessions.append(self._session.currentWidget())

      for cxml in cxmls:
         for sw in sessions:
            sw.setCommandXML(cxml, True)

   def onAddFavorite(self, xml):
      addFavoriteDlg = AddToFavoriteDialog(xml, self)
      addFavoriteDlg.setModel(self._xml_favorite.model)
      addFavoriteDlg.exec()

   def onModifySessionOptions(self):
      if self.sessionOpIndex != None:
         w = self._session.widget(self.sessionOpIndex)
      else:
         w = self._session.currentWidget()
      if w:
         opt = SessionOptionDiag(w.options, "Session Options", self)
         ret = opt.exec()
         if ret == QDialog.DialogCode.Accepted:
            log.debug("new options: %s, ret=%d", opt.options, ret)
            w.setOptions(opt.options)
         del opt

   def onCopySessionOptions(self):
      if self.sessionOpIndex != None:
         w = self._session.widget(self.sessionOpIndex)
      else:
         w = self._session.currentWidget()
      if w:
         SessionOption.copyToClipboard(w.options)

   def _onHelpClicked(self):
      QDesktopServices.openUrl(
          QUrl('http://conf.ruijie.work/pages/viewpage.action?pageId=505610263'))

   def _onAboutClicked(self):
      about = About(self)
      about.exec()

   def _onCheckforUpdates(self):
      return self.versionUpdate.doCheck(True)

   def _onReportIssue(self):
      QDesktopServices.openUrl(QUrl(
          "mailto: lijiaquan@ruijie.com.cn?subject=Issue of NetconfTool&body=What problems are you experiencing?\n\n\nPlease pack the log files in the [%s] directory and send them to me together!" % AppInfo.logdir()))

   def _onActionHistoryToggled(self, checked):
      self.appdata.ui_history = checked

   def _onActionShowStatusBarToggled(self, checked):
      self.statusBar().setHidden(not checked)
      self.appdata.ui_statusbar = checked

   def _onActionShowToolBarToggled(self, checked):
      self.appdata.ui_toolbar = checked

   def _onActionShowDockToggled(self, checked):
      self.appdata.ui_session = checked

   def applyUiConfig(self):
      self.statusBar().setHidden(not self.appdata.ui_statusbar)
      self._dw_favorite.setVisible(self.appdata.ui_session)
      self._dw_history.setVisible(self.appdata.ui_history)
      self.toolBar.setVisible(self.appdata.ui_toolbar)

   def _onImportAppData(self):
      file_dlg = QFileDialog(self)
      file_dlg.setAcceptMode(QFileDialog.AcceptOpen)
      file_dlg.setViewMode(QFileDialog.Detail)
      file_dlg.setFileMode(QFileDialog.ExistingFile)
      file_dlg.setDefaultSuffix("json")
      if file_dlg.exec() == QDialog.Accepted:
         file = file_dlg.selectedFiles()[0]
         log.debug("select file: %s", file)
         try:
            with open(file, 'r') as f:
                ndata = json.load(f)
         except Exception as ex:
            QMessageBox.critical(self, "Import Data", "Invalid config file!\n\n%s" % ex)
         else:
            sel_dlg = AppDataEx("Import Data", ndata, self)
            if sel_dlg.exec() == QDialog.Accepted:
               for key in sel_dlg.selectedTypes:
                  if key == 'session':
                     app_data.addSessions(ndata.get('session', []))
                  elif key == 'history':
                     self._xml_history.addHistorys(ndata.get('history'))
                  elif key == 'favorite':
                     self._xml_favorite.importFavorite(ndata.get('favorite'))
                     app_data.commands = self._xml_favorite.commands()
                  elif key == 'ui-config':
                     self.appdata.ui_conf = ndata.get('ui-config', {})
                     self.applyUiConfig()

   def _onExportAppData(self):
      exp_data = {}
      sel_dlg = AppDataEx("Export Data", app_data.data, self)
      if sel_dlg.exec() == QDialog.Accepted:
         for key in sel_dlg.selectedTypes:
            exp_data[key] = app_data.data.get(key)
         if len(exp_data) == 0:
            return
         file_dlg = QFileDialog(self)
         file_dlg.setAcceptMode(QFileDialog.AcceptSave)
         file_dlg.setViewMode(QFileDialog.Detail)
         file_dlg.setDefaultSuffix("json")
         if file_dlg.exec() == QDialog.Accepted:
            wf = file_dlg.selectedFiles()[0]
            with open(wf, 'w') as f:
               json.dump(exp_data, f, indent=4)
               QMessageBox.information(self, "Export Data", 'export success.\n " %s "' % wf)

   def _onSaveAppData(self):
      app_data.commands = self._xml_favorite.commands()
      app_data.save()

   def _favoritesEdit(self):
      sessions = []
      for id in range(self._session.count()):
         sw = self._session.widget(id)
         session={}
         if sw.connected:
            session[self._session.tabText(id)] = self._session.widget(id)
            sessions.append(session)
      if self.favoritesEditor is None:
         self.favoritesEditor = FavoritesEditor(self._xml_favorite.model, self)
      self.favoritesEditor.setActiveSessionInfo(sessions)
      self.favoritesEditor.activateWindow()
      self.favoritesEditor.raise_()
      self.favoritesEditor.showNormal()

   def closeEvent(self, ev):
      has_active_session = False
      for idx in range(self._session.count()):
         ss = self._session.widget(idx)
         if ss.connected == True:
            has_active_session = True
            break

      if has_active_session is True:
         ret = QMessageBox.question(self, "Exit", "Do you wish to disconnect from all sessions and exit?",
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
         if ret != QMessageBox.Yes:
            return ev.ignore()
      app_data.commands = self._xml_favorite.commands()

def handle_exception(exc_type, exc_value, exc_traceback):
   save_app_data_before_exit()
   traceback_format = traceback.format_exception(exc_type, exc_value, exc_traceback)
   message = "".join(traceback_format)
   log.fatal(f"{message}")

   message = f"An exception of type {exc_type.__name__} occurred.\n{exc_value}\n"
   QMessageBox.critical(None, "Error", message)

   sys.__excepthook__(exc_type, exc_value, exc_traceback)
   sys.exit(1)

def save_app_data_before_exit():
   log.info("save_app_data_before_exit")
   app_data.save()
   his = SearchHistory(False)
   his.saveSearchHistory()

if __name__ == "__main__":
   #guiapp = QGuiApplication(sys.argv)
   #dpi = (guiapp.screens()[0]).logicalDotsPerInch()

   #if dpi > 96.0:
   # QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
   sys.excepthook = handle_exception
   QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
   if sys.platform == 'darwin':
      QCoreApplication.setAttribute(Qt.AA_DontShowIconsInMenus, True)
   #QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

   app = QApplication(sys.argv)
   dpi = app.primaryScreen().logicalDotsPerInch()
   log.info("=================================================================================================")
   log.info("Run in:%s, current exe dir:%s, Home:%s"%(sys.platform, app.applicationDirPath(), QDir.homePath()))
   font = QFont()
   log.info(f"Default font: defaultFamily={font.defaultFamily()}, pixelSize={font.pixelSize()}, pointSize={font.pointSize()}")
   if sys.platform == 'cygwin' or sys.platform == 'win32':
      log.info("set font family to YaHei")
      font.setFamily("微软雅黑")
      app.setFont(font)

   log.info(f"primaryScreen dpi: {dpi}")
   factor = 1
   if dpi >= 96:
      factor = dpi/96
      log.info("Hi DPI mode, dpi=%d, factor=%f" % (dpi, factor))
      log.info("Set Font PixelSize: %d" % int(12 * factor))
      font = app.font()
      font.setPixelSize(int(12 * factor))
      app.setFont(font)

   app.setApplicationName("NetConf Tool")
   if sys.platform == 'darwin':
      app.setWindowIcon(QIcon(':/res/logo.icns'))
   else:
      app.setWindowIcon(QIcon(':/res/logo.ico'))
   # app.setApplicationDisplayName("NetConf Tool")
   window = MainWindow(app_data)
   window.setWindowTitle("NetConf Tool")
   window.setGeometry(0, 0, int(800*factor), int(600*factor))
   window.center()

   # 恢复布局
   qsetting = QSettings(os.path.join(AppData.settingDir(), "ui_setting.ini"), QSettings.IniFormat, window)
   qsetting.beginGroup('layout')

   if qsetting.value('geometry') :
      window.restoreGeometry(qsetting.value('geometry'))

   if qsetting.value('state'):
      window.restoreState(qsetting.value('state'))

   dockwindlist = window.findChildren(QDockWidget)
   for widget in dockwindlist:
      window.restoreDockWidget(widget)
   qsetting.endGroup()

   window.show()
   ret = app.exec()

   # 保存布局
   qsetting.beginGroup('layout')
   qsetting.setValue('geometry', window.saveGeometry())
   qsetting.setValue('state', window.saveState())
   qsetting.endGroup()

   save_app_data_before_exit()
   sys.exit(ret)
