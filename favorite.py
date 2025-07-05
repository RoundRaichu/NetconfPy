import logging
import sys
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import QWidget
from anytree.importer import DictImporter
from qanytree.qanytreeitem import QAnyTreeItem
from PyQt5.QtCore import Qt
from utils import pretty_xml
from xmleditor import XmlEditor, XmlEdit

log = logging.getLogger('netconftool.favorite')

class RowType(object):
    XML = 0
    CATEGORY = 1

class FavoriteModel(QAbstractItemModel):
    def __init__(self, data:dict, parent=None):
        super().__init__(parent)
        importer = DictImporter(nodecls=QAnyTreeItem)
        self.root = importer.import_(data)
        self.undoStack = QUndoStack(self)

    """Overridden functions"""
    def index(self, row, column, parent=QModelIndex()):
        if parent.isValid() and parent.column() != 0:
            return QModelIndex()

        parentItem = self.getItem(parent)
        if not parentItem:
            return QModelIndex()

        childItem = parentItem.getChild(row)
        if childItem:
            return self.createIndex(row, column, childItem)

        return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()

        childItem = self.getItem(index)
        parentItem = childItem.parent

        if not parentItem or parentItem == self.root:
            return QModelIndex()

        return self.createIndex(parentItem.childNumber(), 0, parentItem)

    def rowCount(self, parent=QModelIndex()):
        parentItem = self.getItem(parent)
        if parentItem:
            return parentItem.childCount()

        if not parentItem or parentItem == self.root:
            self.root.childCount()

        return 0

    def insertRows(self, position, rows, parent=QModelIndex()):
        parentItem = self.getItem(parent)
        if not parentItem:
            return False

        self.beginInsertRows(parent, position, position + rows - 1)
        success = parentItem.insertChildren(position, rows, self.root.columnCount())
        self.endInsertRows()

        return success

    def moveRows(self, sourceParent, sourceRow, count, destinationParent, destinationChild):
        newDestinationChild = destinationChild
        if sourceParent == destinationParent:
            if sourceRow == destinationChild:
                return True
            elif sourceRow < destinationChild:
                newDestinationChild += 1

        destinationItem = self.getItem(destinationParent)
        self.beginMoveRows(sourceParent, sourceRow, sourceRow + count - 1, destinationParent, newDestinationChild)
        for row in range(sourceRow, sourceRow + count):
            index = self.index(row, 0, sourceParent)
            item = self.getItem(index)
            item.parent = destinationItem

            destinationItem.moveChild(item.childNumber(), destinationChild)
        self.endMoveRows()

        return True

    def removeRows(self, position, rows, parent=QModelIndex()):
        log.debug(f"removeRows: position={position}, rows={rows}, parent={parent}")
        parentItem = self.getItem(parent)
        if not parentItem:
            return False

        self.beginRemoveRows(parent, position, position + rows - 1)
        success = parentItem.removeChildren(position, rows)
        self.endRemoveRows()

        return success

    def columnCount(self, parent=QModelIndex()):
        return self.root.columnCount()

    def insertColumns(self, position, columns, parent=QModelIndex()):
        self.beginInsertColumns(parent, position, position + columns - 1)
        success = self.root.insertColumns(position, columns)
        self.endInsertColumns()

        return success

    def removeColumns(self, position, columns, parent=QModelIndex()):
        self.beginRemoveColumns(parent, position, position + columns - 1)
        success = self.root.removeColumns(position, columns)
        self.endRemoveColumns()

        if self.root.columnCount() == 0:
            self.removeRows(0, self.rowCount())

        return success

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()

        if role == Qt.DisplayRole or role == Qt.EditRole:
            item = self.getItem(index)
            return item.getData(index.column())

        if role == Qt.DecorationRole and index.column() == 0:
            if self.rowType(index) == RowType.CATEGORY:
                return QIcon(':/res/folder.png')
            else:
                return QIcon(':/res/file.png')
        if role == Qt.ToolTipRole:
            item = self.getItem(index)
            content = item.getData(1)
            if len(content) > 1024:
                return content[:200] + '\n  ...'
            else:
                return item.getData(1)

        return QVariant()

    def setData(self, index, value, role=Qt.EditRole):
        item = self.getItem(index)
        if index.column() > 0 and item.getData(3).value() == 1:
            return False

        result = item.setData(index.column(), value)
        if result:
            self.dataChanged.emit(index, index, [role])

        return result

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.root.getData(section)

        return QVariant()

    def setHeaderData(self, section, orientation, value, role=Qt.EditRole):
        if role != Qt.EditRole or orientation != Qt.Horizontal:
            return False

        result = self.root.setData(section, value)
        if result:
            self.headerDataChanged.emit(orientation, section, section)

        return result

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsDropEnabled

        item3 = self.getItem(self.index(index.row(), 2, index.parent()))
        if index.column() > 0 and item3.getData(2) == 1:
            return Qt.NoItemFlags

        if index.column() > 0 and item3.getData(2) == 0:
            return Qt.ItemNeverHasChildren | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled | Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable | super().flags(index)

        return Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled | Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable | super().flags(index)

    def supportedDropActions(self):
        return Qt.MoveAction

    def rowType(self, index) -> RowType:
        if not index.isValid():
            return RowType.CATEGORY
        item = self.getItem(index)
        if item.getData(2) == 0:
            return RowType.XML
        return RowType.CATEGORY

    """Helper functions"""
    def copyRow(self, sourceParent, sourceRow, destinationParent, destinationChild):
        columns = self.columnCount()
        for column in range(columns):
            destinationIndex = self.index(destinationChild, column, destinationParent)
            sourceIndex = self.index(sourceRow, column, sourceParent)
            self.setData(destinationIndex, self.data(sourceIndex))

    def getItem(self, index):
        if index.isValid():
            item = index.internalPointer()
            if item:
                return item

        return self.root

    def toDict(self):
        return self.root.toDict()

class FavoriteTreeView(QTreeView):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.draggedItem = []
        self.draggedIndexs = []
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        # self.setColumnWidth(0, 30)

        self._act_newCategory = QAction(QIcon(':/res/add-folder.png'), "New Category", self)
        self._act_newCategory.triggered.connect(self._onCreateCategory)

        self._act_newSubCategory = QAction("└ New Category", self)
        self._act_newSubCategory.triggered.connect(lambda: self._onCreateCategory(True))

        self._act_add = QAction(QIcon(':/res/add-file.png'), "New XML", self)
        self._act_add.triggered.connect(self._onNewNode)

        self._act_modify = QAction(QIcon(':/res/edit.png'), "Edit XML", self)
        self._act_modify.triggered.connect(self._onEditNode)

        self._act_delete = QAction(QIcon(':/res/delete.png'), "Delete", self)
        self._act_delete.triggered.connect(self.deleteItem)
        self._act_delete.setShortcut(QKeySequence.StandardKey.Delete)
        self._act_delete.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

        self._act_cut = QAction("Cut", self)
        self._act_cut.setShortcut(QKeySequence.StandardKey.Cut)
        self._act_cut.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._act_cut.triggered.connect(self.cutItem)

        self._act_copy = QAction("Copy", self)
        self._act_copy.setShortcut(QKeySequence.StandardKey.Copy)
        self._act_copy.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._act_copy.triggered.connect(self.copyItem)

        self._act_paste = QAction("Paste", self)
        self._act_paste.setShortcut(QKeySequence.StandardKey.Paste)
        self._act_paste.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._act_paste.triggered.connect(self.pasteItem)

        """将action添加到控件,以便生效快捷键"""
        self.addActions([self._act_cut, self._act_copy, self._act_paste, self._act_delete])

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._onTreeViewMenuRequestd)
        self.setHeaderHidden(True)
        self.setEditTriggers(QAbstractItemView.EditKeyPressed)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._externalAction = []
        self._xmlOtherAction = []
        self._copiedItems = []
        self._cutItemIndex = []
        self.setAutoExpandDelay(300)
        self.setDropIndicatorShown(False)

    def setModel(self, model):
        super().setModel(model)
        # set Only column 0 is Visible
        for i in range(1, model.columnCount()):
            self.setColumnHidden(i, True)

        # Connect model's rowsMoved signal
        try:
            model.rowsMoved.connect(self.rowsMoved, Qt.UniqueConnection)
        except TypeError:
            pass

    def rowsMoved(self, parent, start, end, destination, row):
        if parent == destination and start < row:
            row -= 1

        index = self.model().index(row, 0, parent)
        self.setCurrentIndex(index)

    def dragEnterEvent(self, e):
        indexes = self.selectedIndexes()
        self.draggedItem = []
        for index in indexes:
            self.draggedItem.append(self.itemFromIndex(index))
        self.draggedIndexs = indexes
        e.accept()
        super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if len(self.draggedItem):
            droppedIndex = self.indexAt(e.pos())
            droppedItem = self.itemFromIndex(droppedIndex)
            if droppedItem.childCount() == 0:
                self.expandRecursively(droppedIndex, -1)
            # If drop location is invalid or does not share the dragged item's parent
            # if not droppedIndex.isValid() or droppedItem.parent != self.draggedItem.parent:
            # if not droppedIndex.isValid():
            #     e.ignore()
            #     return
            """检测是否包含重复递归目录"""
            parent = droppedIndex.parent()
            while parent:
                for draggedIndex in self.draggedIndexs:
                    if draggedIndex == parent or draggedIndex == droppedIndex:
                        e.ignore()
                        return
                if parent == QModelIndex():
                    break
                parent = parent.parent()
            e.accept()
        super().dragMoveEvent(e)

    def dropEvent(self, e):
        model = self.model()
        droppedIndex = self.indexAt(e.pos())

        if droppedIndex == QModelIndex():
            """拖到根,添加在最后"""
            newPosition = model.rowCount()
            log.debug(f'will dropped to root: {newPosition}')
        else:
            newPosition = droppedIndex.row()
            log.debug(f'will dropped to row: {newPosition}')

        if model.rowType(droppedIndex) == RowType.CATEGORY and self.isExpanded(droppedIndex):
            destinationParent = droppedIndex
            """如果目标是普通文件夹, 且已展开, 则追加在最前面"""
            if droppedIndex != QModelIndex():
                newPosition = 0
                log.debug(f'dropped to CATEGORY set row: {newPosition}')
        else:
            destinationParent = droppedIndex.parent()

        """拖动后, 保持文件夹队形"""
        realDraggedIndexs = []
        realDraggedItem = []
        for idx, draggedIndex in enumerate(self.draggedIndexs):
            if draggedIndex.parent() not in self.draggedIndexs:
                realDraggedIndexs.append(draggedIndex)
                realDraggedItem.append(self.draggedItem[idx])

        for idx, draggedItem in enumerate(realDraggedItem):
            oldPosition = draggedItem.childNumber()
            self.model().moveRow(realDraggedIndexs[idx].parent(),oldPosition, destinationParent, newPosition + idx)

        self.draggedItem = []
        self.draggedIndexs = []

    def itemFromIndex(self, index):
        return self.model().getItem(index)

    def currentItem(self) -> QAnyTreeItem:
        return self.model().getItem(self.currentIndex())

    def deleteItem(self):
        model = self.model()
        need_question = False
        seletedIndexs = self.selectedIndexes()
        for index in seletedIndexs:
            if model.rowCount(index):
                need_question = True
                break

        if len(seletedIndexs) > 1 or need_question is True:
            result = QMessageBox.question(self, "Delete", "Do you want to delete the selected items?",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if result != QMessageBox.Yes:
                return
        for index in reversed(seletedIndexs):
            self.model().removeRow(index.row(), index.parent())

    def cutItem(self):
        log.debug("cutItem")
        copyItems = []
        cutIndex =[]
        model = self.model()
        xml = ""
        for index in self.selectedIndexes():
            if model.rowType(index) == RowType.XML:
                xml += self.getXml(index) + '\n'
                copyItems.append(self.getItemValue(index))
                cutIndex.append(index)
        if len (copyItems):
            self._copiedItems = copyItems
            self._cutItemIndex = cutIndex
            QApplication.clipboard().setText(xml)

    def copyItem(self):
        log.debug("copyItem")
        copyItems = []
        model = self.model()
        xml = ""
        for index in self.selectedIndexes():
            if model.rowType(index) == RowType.XML:
                xml += self.getXml(index) + '\n'
                copyItems.append(self.getItemValue(index))
        if len (copyItems):
            self._copiedItems = copyItems
            self._cutItemIndex = []
            QApplication.clipboard().setText(xml)

    def pasteItem(self):
        log.debug("pasteItem")
        if len(self._copiedItems):
            for index in reversed(self._cutItemIndex):
                self.model().removeRow(index.row(), index.parent())
            self._cutItemIndex = []

            for item in self._copiedItems:
                log.debug(f"paste name={item[0]}, value={item[1]}")
                self.insertLeaf(item[0], item[1])

    def insertLeaf(self, name, xml):
        index = self.currentIndex()
        model = self.model()

        if model.rowType(index) == RowType.CATEGORY:
            parent = model.index(index.row(), 0, index.parent())
            row = model.rowCount(parent)
            model.insertRows(row, 1, parent)
            row = model.rowCount(parent) - 1
        else:
            row = index.row()+1
            parent = index.parent()
            model.insertRows(row, 1, parent)

        for i, value in enumerate([name, xml, RowType.XML]):
            idx = model.index(row, i, parent)
            model.setData(idx, value)

        cur_index = model.index(row, 0, parent)
        self.setCurrentIndex(cur_index)
        self.edit(cur_index)
        self.expand(parent)

    def insertCategory(self, index, name, to_sub=False):
        model = self.model()
        if to_sub and self.model().rowType(index) == 1:
            row = model.rowCount(index)
            parent = index
        else:
            row = index.row()+1
            parent = index.parent()

        model.insertRows(row, 1, parent)
        for i, value in enumerate([name, "", RowType.CATEGORY]):
            idx = model.index(row, i, parent)
            model.setData(idx, value)

        cur_index = model.index(row, 0, parent)
        self.setCurrentIndex(cur_index)
        self.edit(cur_index)
        self.expand(parent)

    def updateXml(self, index, xml):
        model = self.model()
        dindex = model.index(index.row(), 1, index.parent())
        return model.setData(dindex, xml)

    def getXml(self, index):
        model = self.model()
        dindex = model.index(index.row(), 1, index.parent())
        return model.data(dindex)

    def getItemValue(self, index=None):
        if index is None:
            index = self.currentIndex()
        model = self.model()
        dindex = model.index(index.row(), 1, index.parent())
        value =[]
        for i in range(0, 3):
            dindex = model.index(index.row(), i, index.parent())
            value.append(model.data(dindex))
        log.debug(f"getItemValue: {value}")
        return value

    def _onCreateCategory(self, to_sub=False):
        index = self.currentIndex()
        self.insertCategory(index, "New Category", to_sub)

    def _onNewNode(self):
        self.insertLeaf("NewItem*", "")
        # newdlg = FavoriteXmlEditor("", "New XML", self)
        # ret = newdlg.exec()
        # if ret == QDialog.DialogCode.Accepted:
        #     self.insertLeaf("NewItem*", newdlg.xml())

    def _onEditNode(self):
        index = self.currentIndex()
        if self.model().rowType(index) == RowType.CATEGORY:
            log.info("Category Can't Edit")
            return

        item = self.itemFromIndex(index)
        newdlg = XmlEditor(item.getData(1), "Edit XML - %s"%(item.getData(0)), self)
        ret = newdlg.exec()
        if ret == QDialog.DialogCode.Accepted:
            xml_index = self.model().index(index.row(), 1, index.parent())
            self.model().setData(xml_index, newdlg.xml())

    def setAdditionalActions(self, actions, is_xml_action:bool = False):
        if is_xml_action :
            self._xmlOtherAction.extend(actions)
        else:
            self._externalAction.extend(actions)

    def _onTreeViewMenuRequestd(self, pos: QPoint):
        index = self.indexAt(pos)
        menu = QMenu()

        self._act_paste.setEnabled(True if len(self._copiedItems) else False)

        if index.isValid():
            menu.addAction(self._act_newCategory)
            # 文件夹可见
            if self.model().rowType(index) == RowType.CATEGORY:
                menu.addAction(self._act_newSubCategory)

            menu.addAction(self._act_add)

            """xml可见"""
            if self.model().rowType(index) == RowType.XML:
                menu.addSeparator()
                menu.addAction(self._act_modify)

            menu.addSeparator()
            menu.addAction(self._act_cut)
            menu.addAction(self._act_copy)
            menu.addAction(self._act_paste)
            menu.addSeparator()
            menu.addAction(self._act_delete)
            act_rename = QAction(QIcon(':/res/rename.png'), "Rename", menu)
            act_rename.triggered.connect(lambda: self.edit(self.currentIndex()))
            menu.addAction(act_rename)

            if len(self._xmlOtherAction):
                if self.model().rowType(index) == RowType.XML:
                    menu.addSeparator()
                    menu.addActions(self._xmlOtherAction)
        else:
            menu.addAction(self._act_newCategory)
            menu.addAction(self._act_add)
            menu.addSeparator()
            menu.addAction(self._act_cut)
            menu.addAction(self._act_copy)
            menu.addAction(self._act_paste)
        if len(self._externalAction):
            menu.addSeparator()
            menu.addActions(self._externalAction)

        menu.exec(QCursor.pos())
        del menu

class _favoriteXmlSignals(QObject):
    reSentRequest = pyqtSignal(str)
    activeItemChanged = pyqtSignal(str)
    # xml list
    executeRequest = pyqtSignal(list)
    executeAllRequest = pyqtSignal(list)
    openFavoriteEditor = pyqtSignal(str)
    #open favoriteEditor


class FavoriteDockWidget(QWidget):
    def __init__(self, favorite:dict, parent=None) -> None:
        super().__init__(parent)
        if not favorite:
            favorite['data'] = ['name', 'xml', 'type']
        self._model = FavoriteModel(favorite)
        self._favorite = favorite
        self.signals = _favoriteXmlSignals()
        self._initUI()

    def _initUI(self):
        view = FavoriteTreeView(self)
        view.setModel(self._model)
        view.setSelectionModel(QItemSelectionModel(self._model, self))
        view.selectionModel().currentChanged.connect(self._onViewCurrentChanged)
        view.doubleClicked.connect(self._onDoubleClicked)
        view.clicked.connect(self._onViewCurrentChanged)

        # addition actions on view
        act_execute = QAction(QIcon(':/res/flash.png'), "Execute", self)
        act_execute.triggered.connect(lambda: self._onExecuteRequst(False))
        act_execute.setShortcut('Ctrl+E')
        view.addAction(act_execute)
        # act_execute.setShortcutContext(Qt.WidgetShortcut)

        act_executeall = QAction("Execute All Sessions", self)
        act_executeall.triggered.connect(lambda: self._onExecuteRequst(True))
        act_executeall.setShortcut('Ctrl+Shift+E')
        view.addAction(act_executeall)

        view.setAdditionalActions([act_execute, act_executeall], True)

        act_openInFavoriteEditor = QAction("Open Favorites Editor", self)
        act_openInFavoriteEditor.triggered.connect(
            lambda: self.signals.openFavoriteEditor.emit(""))
        view.setAdditionalActions([act_openInFavoriteEditor])

        # TODO: export sub Category
        # act_export = QAction("Export", self)
        # act_export.triggered.connect(self._export_node)
        # act_export.setEnabled(False)
        # view.addAction(act_export)

        vlayout = QVBoxLayout(self)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.addWidget(view)

        self._treeview = view

    def _onDoubleClicked(self, index):
        item = self._treeview.currentItem()
        if self._model.rowType(index) == RowType.XML:
            self.signals.reSentRequest.emit(item.getData(1))

    def _onViewCurrentChanged(self, current: QModelIndex):
        if self._model.rowType(current) == RowType.XML:
            intem = self._model.getItem(current)
            self.signals.activeItemChanged.emit(intem.getData(1))

    def _onCurrentItemChanged(self, index):
        item = self._treeview.currentItem()
        if self._model.rowType(index) == RowType.XML:
            self.signals.activeItemChanged.emit(item.getData(1))

    def _onExecuteRequst(self, to_all: False):
        cxmls = []
        indexs = self._treeview.selectedIndexes()
        for index in indexs:
            if self._model.rowType(index) == RowType.CATEGORY:
                continue
            cxmls.append(self._treeview.getXml(index))
        if to_all:
            ret = QMessageBox.question(self, "Execute All Sessions", "Do you want to execute seleted item to all connected session?",
                                       QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret == QMessageBox.Yes:
                self.signals.executeAllRequest.emit(cxmls)
        else:
            self.signals.executeRequest.emit(cxmls)

    @property
    def model(self):
        return self._model

    def _export_node(self):
        model = self._treeview.model()
        self._favorite = model.toDict()

    def commands(self):
        return self._treeview.model().toDict()

    def __appyNode(self, index, children: list):
        for child in children:
            data = child.get('data')
            if data[2] == 1:
                self._treeview.insertCategory(index, data[0])
                index = self._treeview.currentIndex()
                self.__appyNode(index, child.get('children', []))
            else:
                self._treeview.insertLeaf(data[0], data[1])
                index = self._treeview.currentIndex()

    def importFavorite(self, data: dict):
        row = self._model.rowCount()
        model = self._model
        index = model.createIndex(row - 1, 0, model.root)
        return self.__appyNode(index, data.get('children', []))

class FavoritesEditor(QDialog):
    def __init__(self, model, parent=None, flags=Qt.Window) -> None:
        super().__init__(parent, flags)
        self.setModal(False)
        self.setWindowTitle("Edit Favorites")
        if sys.platform == 'cygwin' or sys.platform == 'win32':
            self.setWindowIcon(QIcon(':/res/add-to-favorites.png'))
        log.info('Open FavoritesEditor')
        log.debug("  loadconfig: %s", model.toDict())
        view = FavoriteTreeView(self)
        if model:
            view.setModel(model)
            view.setSelectionModel(QItemSelectionModel(model, self))
            view.selectionModel().currentChanged.connect(self._onViewCurrentChanged)

        editor = XmlEdit(self, 'Favorites')
        # editor.setLineWrapMode(QTextEdit.NoWrap)
        namelable = QLabel("Content", self)

        response = XmlEdit(self, 'response')
        response.setReadOnly(True)
        # response.setLineWrapMode(QTextEdit.NoWrap)
        response.setLimitShow(True)

        bt_format = QPushButton("PrettyFormat", self)
        bt_format.clicked.connect(self._onFromatXml)

        bt_send = QPushButton("QuickCheck")
        bt_send.clicked.connect(self._onExecuteXmlRequest)
        bt_send.setDefault(True)
        cb_session = QComboBox(self)

        self._editor = editor
        self._response = response
        self._treeview = view
        self._namelable = namelable
        self._model = model
        self._cb_session = cb_session

        left_frame = QFrame(self)
        llayout = QVBoxLayout(left_frame)
        llayout.setContentsMargins(0, 0, 0, 0)
        llayout.addWidget(QLabel("Favorites:", self))
        llayout.addWidget(view)
        ru_frame = QFrame(self)
        rsplitter = QSplitter(Qt.Orientation.Vertical, self)
        rulayout = QVBoxLayout(ru_frame)
        rulayout.setContentsMargins(0, 0, 0, 0)
        rulayout.addWidget(namelable)
        rulayout.addWidget(editor, 3)
        rsplitter.addWidget(ru_frame)

        rd_frame = QFrame(self)
        rdlayout = QVBoxLayout(rd_frame)
        rdlayout.setContentsMargins(0, 0, 0, 0)
        rdlayout.addWidget(QLabel("Respones:"))
        rdlayout.addWidget(response, 1)
        rsplitter.addWidget(rd_frame)

        rsplitter.setStretchFactor(0, 10)
        rsplitter.setStretchFactor(1, 2)

        blayout = QHBoxLayout()
        blayout.addWidget(bt_format)
        blayout.addSpacing(500)
        blayout.addStretch(2)
        blayout.addWidget(QLabel("Session:", self))
        blayout.addWidget(cb_session, 1)
        blayout.addWidget(bt_send)

        mlayout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        # splitter.setHandleWidth(0)
        splitter.addWidget(left_frame)
        splitter.addWidget(rsplitter)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)

        mlayout.addWidget(splitter)
        mlayout.addLayout(blayout)

    def setModel(self, model) -> None:
        self._treeview.setModel(model)
        self._treeview.setCurrentIndex(self._treeview.model().index(0,0))

    def setActiveSessionInfo(self, sessions:list):
        self._sessions=sessions
        self._cb_session.clear()
        for sesion in sessions:
            for name, sw in sesion.items():
                self._cb_session.addItem(name, sw)

    def _onExecuteXmlRequest(self):
        sw = self._cb_session.currentData()
        if sw and sw.connected:
            resp = sw.setCommandXML(self._editor.toPlainText(), True)
            self._response.setXml(resp.xml)

    def _onFromatXml(self):
        ret, estr = self._editor.prettyFormat()
        if ret is False:
            QMessageBox.information(self, "Syntax error ", "syntax error: %s"%estr)
            return False
        return True

    def _onViewCurrentChanged(self, current: QModelIndex, previous: QModelIndex):
        log.debug("current:%d, %d, previous:%d, %d", current.row(), current.column(), previous.row(), previous.column())
        if self._model.rowType(previous) == RowType.XML:
            self._treeview.updateXml(previous, self._editor.toPlainText())

        current_item = self._model.getItem(current)
        if self._model.rowType(current) == RowType.XML:
            self._editor.setXml(current_item.getData(1))

    def keyPressEvent(self, a0: QKeyEvent) -> None:
        if a0.key() == Qt.Key_Exit or a0.key() == Qt.Key_Escape:
            return a0.ignore()

        return super().keyPressEvent(a0)

    def closeEvent(self, a0: QCloseEvent) -> None:
        index = self._treeview.currentIndex()
        if index.isValid():
            if self._model.rowType(index) == RowType.XML:
                self._treeview.updateXml(index, self._editor.toPlainText())
        log.info("exit FavoritesEditor.")
        log.debug("  newconfig: %s", self._model.toDict())
        return super().closeEvent(a0)

    def _onEditorTextChanged(self):
        self._namelable.setText("Content*")



class AddToFavoriteDialog(QDialog):
    def __init__(self, newxml, parent=None, flags=Qt.Dialog | Qt.WindowCloseButtonHint) -> None:
        super().__init__(parent, flags)
        self.setWindowTitle("Add to Favorites")
        self.setWindowIcon(QIcon(':/res/add-to-favorites.png'))
        view = FavoriteTreeView(self)
        view.pressed.connect(self._onViewPressed)

        name_editor = QLineEdit(self)
        name_editor.setText("NewItem*")
        name_editor.textChanged.connect(self._nameBlankCheck)

        bt_add = QPushButton("Add", self)
        bt_add.clicked.connect(self._onClickedAdd)
        bt_add.setAutoDefault(True)

        bt_update = QPushButton("Update", self)
        bt_update.clicked.connect(self._onClickedUpdate)
        bt_update.setEnabled(False)

        hlayout =QHBoxLayout()
        hlayout.addWidget(QLabel("Save as:", self))
        hlayout.addWidget(name_editor, 1)
        hlayout.addWidget(bt_update)
        hlayout.addWidget(bt_add)

        vlayout = QVBoxLayout(self)
        vlayout.addWidget(view)
        vlayout.addLayout(hlayout)

        self._treeview = view
        self._name = name_editor
        self._bt_add = bt_add
        self._bt_update = bt_update
        self._newXml = newxml

    def setModel(self, model) -> None:
        self._treeview.setModel(model)
        self._treeview.setCurrentIndex(self._treeview.model().index(0,0))

    def _onClickedAdd(self):
        self._treeview.insertLeaf(self._name.text(), pretty_xml(self._newXml, True))
        self.accept()

    def _onClickedUpdate(self):
        index = self._treeview.currentIndex()
        if self._treeview.model().rowType(index) == RowType.CATEGORY:
            QMessageBox.information(self, "Info", "Category Can't Edit")
        else:
            self._treeview.updateXml(index, self._newXml)
            self.accept()

    def _onViewPressed(self, index):
        if self._treeview.model().rowType(index) == RowType.CATEGORY:
            self._bt_update.setEnabled(False)
        else:
            self._name.setText(self._treeview.model().data(index))
            self._bt_update.setEnabled(True)

    def _nameBlankCheck(self, text: str):
        if len(text):
            enable = True
        else:
            enable = False
        self._bt_add.setEnabled(enable)
        index = self._treeview.currentIndex()
        if self._treeview.model().rowType(index) == RowType.XML:
            self._bt_update.setEnabled(enable)


if __name__ == "__main__":
    from data import AppData
    import res_rc
    app_data=AppData()
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d: %(message)s',
                        level=logging.DEBUG)
    class MainWindow(QMainWindow):

        def __init__(self, parent=None):
            super().__init__(parent)
            data1 = {
                'data': [
                    'name', 'xml', 'type'
                    ],
            }
            model = FavoriteModel(app_data.commands)
            view = FavoriteDockWidget(data1)
            editor = FavoritesEditor(model)

            self.setCentralWidget(editor)

    app = QApplication([])
    mainWindow = MainWindow()
    mainWindow.show()
    app.exec()