import typing
from PyQt5.QtCore import *
from PyQt5.QtCore import QModelIndex, QObject, Qt
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from xmleditor import XmlEdit
from ncclient.xml_ import *
from utils import pretty_xml
import logging

log = logging.getLogger('netconftool.session_history')

class SessionOperType(int):
    In = 0
    Out = 1
    Session = 2
    Notification = 3
    TYPE_MAX=4

SessionOperString = ['Receive', 'Send', 'Session', 'Notification', 'unknown']

class SessionHistoryModel(QAbstractItemModel):
    def __init__(self, parent: QObject = None ) -> None:
        super().__init__(parent)
        self._historys = []
        self.horizontalHeader = ['Time', 'Type', 'Brief Info', 'origin xml']

    def rowCount(self, parent: QModelIndex = ...) -> int:

        return len(self._historys)

    def columnCount(self, parent: QModelIndex = ...) -> int:
        return len(self.horizontalHeader)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = ...):
        if role != Qt.DisplayRole:
            return super().headerData(section, orientation, role)

        if orientation == Qt.Orientation.Horizontal:
            return self.horizontalHeader[section]

        return super().headerData(section, orientation, role)

    def data(self, index: QModelIndex, role: int = ...):
        if not index.isValid():
            return QVariant()
        if role == Qt.DisplayRole or role == Qt.ToolTipRole:
            if index.column() == 1:
                return SessionOperString[self._historys[index.row()][index.column()]]
            else:
                return self._historys[index.row()][index.column()]
        if role == Qt.UserRole:
            return self._historys[index.row()][3]

        return QVariant()

    def setData(self, index: QModelIndex, value: typing.Any, role: int = ...) -> bool:
        if role == Qt.UserRole:
            self._historys[index.row()][4] = value
            return True
        return False

    def index(self, row: int, column: int, parent: QModelIndex = ...) -> QModelIndex:
        if (row < 0 or row > len(self._historys)) or (column < 0 or column > len(self.horizontalHeader)):
            return QModelIndex()

        return self.createIndex(row, column)
        # return super().index(row, column, parent)

    def insertRows(self, row: int, count: int, parent: QModelIndex = ...) -> bool:
        if count == 0:
            return False

        if parent.isValid():
            self.beginInsertRows(parent, row, row + count - 1)
        else:
            self.beginInsertRows(QModelIndex(), row, row + count - 1)
        for ar in range(row, row + count, 1):
            self._historys.insert[ar, ["","","",""]]
        self.endInsertRows()
        return True

    def removeRows(self, row: int, count: int, parent: QModelIndex = ...) -> bool:
        if count == 0:
            return False
        if parent.isValid():
            self.beginRemoveRows(parent, row, row + count - 1)
        else:
            self.beginRemoveRows(QModelIndex(), row, row + count - 1)

        # log.debug("removeRows: row %d, count:%d", row, count)
        for ar in range(row, row + count, 1):
            self._historys.pop(row)

        self.endRemoveRows()
        return True

    def appendRow(self, Timestamp: str, Direction: str, Brief: str, origin: str):
        ntf = [Timestamp, Direction, Brief, origin]
        self.beginInsertRows(QModelIndex(), self.rowCount(), self.rowCount())
        self._historys.append(ntf)
        self.endInsertRows()

    def clear(self):
        self.beginResetModel()
        self._historys.clear()
        self.endResetModel()

class _SessionHistorySignals(QObject):
    countChanged = pyqtSignal(int)

class SessionHistoryWidget(QWidget):
    "通告显示控件"
    def __init__(self, parent=None, flags=Qt.Widget) -> None:
        super().__init__(parent, flags)
        self.signal = _SessionHistorySignals()
        self._initUI()

        timer = QTimer(self)
        timer.setInterval(1000 * 30)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self.setFlowUpMode(True))

        self._flowUpMode = True
        self._flowUpTimer = timer

    def _initUI(self):
        sessionHistoryList = QTableView(self)
        sessionHistoryList.setStyleSheet("QTableView::item{padding-left:10px;padding-right:10px;}")
        sessionHistoryList.setAlternatingRowColors(True)
        sessionHistoryList.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        datamodel = SessionHistoryModel(self)
        proxy_model = QSortFilterProxyModel(self)
        proxy_model.setSourceModel(datamodel)
        proxy_model.setFilterKeyColumn(3)

        sessionHistoryList.setModel(proxy_model)
        sessionHistoryList.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        sessionHistoryList.setSelectionModel(QItemSelectionModel(proxy_model, self))
        sessionHistoryList.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        sessionHistoryList.selectionModel().currentChanged.connect(self._onCurrentChanged)
        sessionHistoryList.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        sessionHistoryList.customContextMenuRequested.connect(self._onCustomMenuRequest)

        sessionHistoryList.hideColumn(3)

        sessionHistoryList.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        sessionHistoryList.horizontalHeader().setStretchLastSection(True)
        sessionHistoryList.horizontalHeader().setDefaultSectionSize(100)
        # sessionHistoryList.horizontalHeader().resizeSection(0, 180)

        sessionHistoryList.verticalHeader().setDefaultSectionSize(8)
        sessionHistoryList.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)

        preview = XmlEdit(self, "Session History")
        # preview.setLineWrapMode(QTextEdit.NoWrap)
        preview.setReadOnly(True)
        preview.setLimitShow(True)

        bt_filter = QCheckBox("Filter", self)
        bt_filter.setChecked(True)
        bt_filter.stateChanged.connect(self._onBtFilterStateChanged)

        filter_edit = QLineEdit(self)
        filter_edit.textChanged.connect(self._onFilterChanged)
        filter_edit.setPlaceholderText("Regular expression")

        hlayout = QHBoxLayout()
        hlayout.setContentsMargins(0, 0, 0, 0)
        hlayout.addSpacing(5)
        hlayout.addWidget(bt_filter)
        hlayout.addWidget(filter_edit)

        left_frame = QFrame(self)
        llayout = QVBoxLayout(left_frame)
        llayout.setContentsMargins(0, 0, 0, 0)
        llayout.addLayout(hlayout)
        llayout.addWidget(sessionHistoryList)

        right_frame = QFrame(self)
        rlayout = QVBoxLayout(right_frame)
        rlayout.setContentsMargins(0, 0, 0, 0)
        rlayout.addWidget(preview)

        splitter = QSplitter(self)
        splitter.setHandleWidth(2)
        splitter.addWidget(left_frame)
        splitter.addWidget(right_frame)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        act_copy = QAction("&Copy to Clipboard", self)
        act_copy.triggered.connect(self._onCopy)
        act_copy.setShortcut(QKeySequence.Copy)
        act_copy.setShortcutContext(Qt.WidgetShortcut)

        sessionHistoryList.addAction(act_copy)

        self._preview = preview
        self._bt_filter = bt_filter
        self._filter_edit = filter_edit
        self._proxy_model = proxy_model
        self.datamodel = datamodel
        self.sessionHistoryList = sessionHistoryList
        self._actCopy = act_copy

    def _onCustomMenuRequest(self, pos: QPoint):
        menu = QMenu(self)
        # act_delete = QAction("Delete", menu)
        # act_delete.triggered.connect(self._onDeleteItem)

        act_deleteAll = QAction("Clear Entries", menu)
        act_deleteAll.triggered.connect(self._onDeleteAll)

        act_export = QAction("Export to File...")
        act_export.triggered.connect(self._onExport)

        index = self.sessionHistoryList.indexAt(pos)
        # if index.isValid():
        #     menu.addAction(act_delete)
        if index.isValid():
            menu.addAction(self._actCopy)

        if not len(self.sessionHistoryList.selectedIndexes()):
            act_export.setEnabled(False)

        if self._proxy_model.rowCount() < 1:
            act_deleteAll.setEnabled(False)

        menu.addAction(act_export)
        menu.addSeparator()
        menu.addAction(act_deleteAll)

        menu.exec(QCursor.pos())

    def _onDeleteItem(self):
        sel_indexs = self.sessionHistoryList.selectedIndexes()
        self._proxy_model.removeRows(sel_indexs[0].row(), int(len(sel_indexs)/3))
        self.signal.countChanged.emit(self.datamodel.rowCount())

    def _onDeleteAll(self):
        self.datamodel.clear()
        self._preview.clear()
        self.signal.countChanged.emit(self.datamodel.rowCount())

    def _selectItemToText(self):
        sel_indexs = self.sessionHistoryList.selectedIndexes()
        rows = []
        for oidx in sel_indexs:
            idx = self._proxy_model.mapToSource(oidx)
            if idx.row() not in rows:
                rows.append(idx.row())
        text = ""
        for row in rows:
            time_idx = self.datamodel.index(row, 0)
            dir_idx = self.datamodel.index(row, 1)
            brief_idx = self.datamodel.index(row, 2)

            title = "<!-- Time=%s, Type=%s, Brief Info=%s -->\n"%(
                self.datamodel.data(time_idx, Qt.DisplayRole),
                self.datamodel.data(dir_idx, Qt.DisplayRole),
                self.datamodel.data(brief_idx, Qt.DisplayRole))
            text += title
            text += pretty_xml(self.datamodel.data(time_idx, Qt.UserRole))
            text += "\n\n"
        return text

    def _onCopy(self):
        QApplication.clipboard().setText(self._selectItemToText())

    def _onExport(self):
        file_dlg = QFileDialog(self)
        file_dlg.setAcceptMode(QFileDialog.AcceptSave)
        file_dlg.setViewMode(QFileDialog.Detail)
        file_dlg.setDefaultSuffix("xml")
        if file_dlg.exec() == QDialog.Accepted:
            wf = file_dlg.selectedFiles()[0]
            with open(wf, 'w') as f:
                f.write(self._selectItemToText())
                QMessageBox.information(self, "Export", 'export success.\n " %s "' % wf)

    def setFlowUpMode(self, mode: bool):
        log.debug("flowup %s", mode)
        self._flowUpMode = mode

    def appendHistory(self, time:QDateTime, Direction: str, xml: str, Brief = None, extra = None):
        if self.datamodel.rowCount() > 9999:
            log.info(f"The session history is reached 10000, no new records were added")
            return

        recevied_time = time.toString("yyyy-MM-dd hh:mm:ss.zzz")
        if Brief is None:
            ntf = to_ele(xml)
            msg_id = ntf.get("message-id")
            msg_id = f'[{msg_id}] ' if msg_id is not None else ""
            pname = msg_id + '<' + etree.QName(ntf).localname + '>'
            for child in ntf:
                pname = f'{pname}<{etree.QName(child).localname}>'
            brief = pname
        else:
            brief = Brief

        if extra:
            brief = f"{brief} {extra}"

        xml_size = int(len(xml)/1024)
        if xml_size > 50:
            size_str = '{:,}'.format(xml_size)
            xml = f'The size of this reply is {size_str} KB, No specific content is saved.'
        self.datamodel.appendRow(recevied_time, Direction, brief, xml)

        rowcount = self._proxy_model.rowCount();
        if self._flowUpMode or rowcount == 1:
            row = rowcount - 1
            urow = 0 if row < 0 else row
            colum = self.sessionHistoryList.currentIndex().column()
            ucolum = 0 if colum < 0 else colum
            log.debug("setCurrentIndex: %d, %d", urow, ucolum)
            self.sessionHistoryList.setCurrentIndex(self._proxy_model.index(urow, ucolum))

        # 第一次收到数据，做一次宽度调整
        if rowcount <= 1:
            self.sessionHistoryList.resizeColumnToContents(0)
            # self.sessionHistoryList.resizeColumnToContents(1)

        self.signal.countChanged.emit(self.datamodel.rowCount())

    def _onCurrentChanged(self, index: QModelIndex):
        if index.row() != self._proxy_model.rowCount()-1:
            self.setFlowUpMode(False)
            self._flowUpTimer.start()
        else:
            self.setFlowUpMode(True)

        index = self._proxy_model.mapToSource(index)

        """如果当前preview窗口不可见, 先不更新preview内容, 等showEvent触发更新"""
        if index.isValid() and self._preview.isVisible():
            self._preview.setXml(self.datamodel.data(index, Qt.UserRole))

    def _onBtFilterStateChanged(self, sta: int):
        ftext =""
        if sta == 2:
            ftext = self._filter_edit.text()
        regExp = QRegExp(ftext, Qt.CaseInsensitive, QRegExp.PatternSyntax.WildcardUnix)
        self._proxy_model.setFilterRegExp(regExp)

    def _onFilterChanged(self, s: str):
        if self._bt_filter.isChecked():
            regExp = QRegExp(s, Qt.CaseInsensitive, QRegExp.PatternSyntax.WildcardUnix)
            self._proxy_model.setFilterRegExp(regExp)

    def showEvent(self, a0):
        log.debug(f"showEvent: {a0}")
        oindex = self.sessionHistoryList.currentIndex()
        index = self._proxy_model.mapToSource(oindex)
        if index.isValid():
            self._preview.setXml(self.datamodel.data(index, Qt.UserRole))

        return super().showEvent(a0)