import os, json
from PyQt5.QtCore import *
from PyQt5.QtCore import QModelIndex
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5.QtWidgets import QWidget
from ncclient.xml_ import *
from xmleditor import XmlEdit
import utils

import logging
log = logging.getLogger('netconftool.history')

class HistoryModel(QAbstractListModel):
    def __init__(self, his: list, parent=None) -> None:
        super().__init__(parent)
        self._history = his

    def rowCount(self, parent: QModelIndex = ...) -> int:
        return len(self._history)

    def data(self, index: QModelIndex, role = Qt.DisplayRole) -> QVariant:
        if role == Qt.DisplayRole:
            his = self._history[index.row()]
            if len(his) > 100:
                his = his[:97] + '...'
            return "[%02d] " % index.row() + his

        elif role == Qt.UserRole:
            return self._history[index.row()]

        elif role == Qt.ToolTipRole:
            content = self._history[index.row()]
            if len(content) > 1024:
                return ""
            else:
                return utils.pretty_xml(content, True)

        # elif role == Qt.ItemDataRole.FontRole:
        #     return QFontDatabase.systemFont(QFontDatabase.GeneralFont)

        # elif role == Qt.ItemDataRole.BackgroundColorRole:
        #     if index.row() & 1:
        #         return QColor(192, 192, 192)

        return None

    def removeRow(self, row: int, parent: QModelIndex = ...) -> bool:
        if row < 0:
            return False;
        self.beginRemoveRows(parent, row, row)
        self._history.remove(self._history[row])
        self.endRemoveRows()
        return True

    def batchRemoveRows(self, rows: list, parent: QModelIndex = ...)->bool:
        self.beginResetModel()
        itemlist = []
        for index in rows:
            itemlist.append(self._history[index.row()])
        for item in itemlist:
            self._history.remove(item)
        self.endResetModel()
        return True

    def addHistory(self, his: str):
        self.beginResetModel()
        for h in self._history:
            if h == his:
                self._history.remove(h)
                break
        if len(self._history) > 1000:
            del(self._history[999:])
        self._history.insert(0, his)
        self.endResetModel()

    def deleteAll(self):
        self.beginResetModel()
        self._history.clear()
        self.endResetModel()
class _xmlHistorySignals(QObject):
    reSentRequest = pyqtSignal(str)
    addToFavorite = pyqtSignal(str)

class XmlHistory(QWidget):
    def __init__(self, his=[], parent=None) -> None:
        super().__init__(parent)
        self._listview = QListView(self)
        self.signals = _xmlHistorySignals()
        self._listview.doubleClicked.connect(self._onreSentRequest)
        self._listview.setAlternatingRowColors(True)
        action_favorite = QAction("Add to Favorites", self)
        if not sys.platform == 'darwin':
            action_favorite.setIcon(QIcon(':/res/add-to-favorites.png'))
        action_favorite.triggered.connect(self._addFavorite)
        action_delete = QAction("Delete", self)
        action_delete.triggered.connect(self._deleteItem)
        action_clearall = QAction("Delete All", self)
        action_clearall.triggered.connect(self._deleteItemAll)
        action_copy = QAction("&Copy to Clipboard", self)
        action_copy.setShortcut(QKeySequence.Copy)
        action_copy.setShortcutContext(Qt.WidgetShortcut)
        action_copy.triggered.connect(self._historyCopy)
        action_export = QAction("Export...", self)
        action_export.triggered.connect(self._onHistoryExport)

        self._listview.addActions([action_favorite, action_copy, action_export, action_delete, action_clearall])
        self._listview.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)

        self._preview = XmlEdit(self, 'Preview')
        # self._preview.setLineWrapMode(QTextEdit.NoWrap)
        # self._preview.setFont(
        #     QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self._preview.setReadOnly(True)
        self._preview.setLimitShow(True)

        hlayout = QHBoxLayout()
        hlayout.setContentsMargins(0,0,0,0)
        self._bt_filter = QCheckBox("Filter", self)
        self._bt_filter.stateChanged.connect(self._onBtFilterStateChanged)
        hlayout.addWidget(self._bt_filter)

        self._filter_edit = QLineEdit(self)
        self._filter_edit.textChanged.connect(self._onFilterChanged)
        self._filter_edit.setPlaceholderText("Regular expression")

        self._proxy_model = QSortFilterProxyModel(self)
        self._data_model = HistoryModel(his, self)
        self._proxy_model.setSourceModel(self._data_model)
        self._proxy_model.setFilterKeyColumn(0)
        self._proxy_model.setFilterRole(Qt.UserRole)
        self._listview.setModel(self._proxy_model)
        self._listview.setSelectionModel(QItemSelectionModel(self._proxy_model, self))
        self._listview.selectionModel().currentChanged.connect(self._onCurrentChanged)
        self._listview.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._listview.clicked.connect(self._onCurrentChanged)

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setContentsMargins(0,0,0,0)
        hlayout.addWidget(self._filter_edit)
        his_group = QFrame(self)
        his_group.setContentsMargins(0,0,0,0)
        vlayout1 = QVBoxLayout()
        vlayout1.setContentsMargins(0, 0, 0, 0)
        vlayout1.addLayout(hlayout)
        vlayout1.addWidget(self._listview, 1)
        his_group.setLayout(vlayout1)
        splitter.addWidget(his_group)

        privew_group = QFrame(self)
        privew_group.setContentsMargins(0,0,0,0)
        vlayout2 = QVBoxLayout()
        vlayout2.addSpacing(10)
        vlayout2.setContentsMargins(0, 0, 0, 0)
        vlayout2.addWidget(QLabel("Preview", self))
        vlayout2.addWidget(self._preview)
        privew_group.setLayout(vlayout2)
        splitter.addWidget(privew_group)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setHandleWidth(0)

        vlayout = QVBoxLayout(self)
        vlayout.addWidget(splitter)
        vlayout.setContentsMargins(0, 0, 0, 0)

    def setPreview(self, xml: str):
        if self._preview.isVisible() is False:
            return
        self._preview.setXml(xml)

    # return data model index
    def _modelIndexTransfer(self, proxyIndex: QModelIndex) -> QModelIndex:
        return self._proxy_model.mapToSource(proxyIndex)

    def addHistory(self, hist: str):
        if len(hist) < 512*1024:
            cxml = utils.pretty_xml(hist, pretty_print=False)
            self._data_model.addHistory(cxml)
        else:
            log.info("Try to add history more then 512K, skip")


    def addHistorys(self, hlist: list):
        for h in hlist:
            self.addHistory(h)

    def _onCurrentChanged(self, index: QModelIndex):
        index = self._modelIndexTransfer(index)
        self._preview.setXml(self._data_model.data(index, Qt.UserRole))

    def _addFavorite(self):
        index = self._modelIndexTransfer(self._listview.currentIndex())
        self.signals.addToFavorite.emit(
            self._data_model.data(index, Qt.UserRole))
        pass

    def _deleteItem(self):
        indexs = []
        for index in self._listview.selectedIndexes():
            indexs.append(self._modelIndexTransfer(index))
        if len(indexs) == 0:
            return
        self._data_model.batchRemoveRows(indexs)
        self._listview.setCurrentIndex(self._data_model.index(indexs[0].row(), 0))

    def _deleteItemAll(self):
        if self._data_model.rowCount() == 0:
            return
        ret = QMessageBox.warning(self, "Warning", "Are you sure to delete all history?",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret == QMessageBox.Yes:
            self._data_model.deleteAll()
            self._preview.clear()

    def _onreSentRequest(self):
        index = self._modelIndexTransfer(self._listview.currentIndex())
        self.signals.reSentRequest.emit(self._data_model.data(index, Qt.UserRole))

    def _onFilterChanged(self, s: str):
        if self._bt_filter.isChecked():
            regExp = QRegExp(s, Qt.CaseInsensitive,
                             QRegExp.PatternSyntax.WildcardUnix)
            self._proxy_model.setFilterRegExp(regExp)

    def _onBtFilterStateChanged(self, sta: int):
        ftext =""
        if sta == 2:
            ftext = self._filter_edit.text()
        regExp = QRegExp(ftext, Qt.CaseInsensitive,
                         QRegExp.PatternSyntax.WildcardUnix)
        self._proxy_model.setFilterRegExp(regExp)

    def _historyCopy(self):
        indexs = self._listview.selectedIndexes()
        if len(indexs) == 0:
            return
        text = ""
        for index in indexs:
            index = self._modelIndexTransfer(index)
            text += utils.pretty_xml(self._data_model.data(index, Qt.UserRole), True) + "\n"
        QApplication.clipboard().setText(text)

    def _onHistoryExport(self):
        indexs = self._listview.selectedIndexes()
        if len(indexs) == 0:
            return
        history=[]
        for index in indexs:
            index = self._modelIndexTransfer(index)
            history.append(self._data_model.data(index, Qt.UserRole))
        exp_data = {}
        exp_data['history'] = history
        file_dlg = QFileDialog(self)
        file_dlg.setAcceptMode(QFileDialog.AcceptSave)
        file_dlg.setViewMode(QFileDialog.Detail)
        file_dlg.setDefaultSuffix("json")
        if file_dlg.exec() == QDialog.Accepted:
            wf = file_dlg.selectedFiles()[0]
            with open(wf, 'w') as f:
                json.dump(exp_data, f, indent=4)
                QMessageBox.information(self, "Export", 'export success.\n " %s "' % wf)

if __name__ == "__main__":
    app = QApplication([])
    widget = XmlHistory()
    widget.show()
    app.exec()