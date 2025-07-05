import typing
from PyQt5 import QtCore
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QPushButton, QVBoxLayout, QWidget
import utils
from ncclient.xml_ import to_ele
import logging
from data import SearchHistory

log = logging.getLogger('netconftool.xmleditor')

class HighlightingRule(object):
    def __init__(self, regexp, fcolor=Qt.color1, bold=False) -> None:
        self._pattern = QRegExp(regexp)
        self._pattern.setMinimal(True)
        self._format = QTextCharFormat()
        self._format.setFontWeight(
            QFont.Bold if bold is True else QFont.Normal)
        self._format.setForeground(fcolor)
    @property
    def pattern(self):
        return self._pattern

    @property
    def format(self):
        return self._format

class XmlHighlighter(QSyntaxHighlighter):
    def __init__(self, parent: QtCore.QObject) -> None:
        super().__init__(parent)
        self._rules =[]
        # rule1 = HighlightingRule(Qt.blue, '\".*\"')
        # xmlElementRegex
        self._rules.append(HighlightingRule(r'<[?\s]*[/]?[\s]*([^\n][^>]*)(?=[\s/>])',
                                            Qt.blue))
        # xmlAttributeRegex
        self._rules.append(HighlightingRule(r'[\w:|-]+\w+(?=\=)',
                                            Qt.darkGreen))
        # xmlValueRegex
        self._rules.append(HighlightingRule(r'\"[^\n\"]+\"(?=[?\s/>])',
                                            Qt.darkRed))
        # xmlkeywords
        for reg in ['<\\?', '/>', '>', '<', '</', '\\?>']:
            self._rules.append(HighlightingRule(reg, Qt.red))

    def highlightBlock(self, text: str):
        for rule in self._rules:
            exp = QRegExp(rule.pattern)
            index = exp.indexIn(text)
            while index >= 0:
                len = exp.matchedLength()
                self.setFormat(index, len, rule.format)
                index = exp.indexIn(text, index + len)
        self.setCurrentBlockState(0)

class XmlEdit(QPlainTextEdit):
    def __init__(self, parent=None, objname="") -> None:
        super().__init__(parent)
        self.setObjectName(objname)
        myHighlighter = XmlHighlighter(self)
        myHighlighter.setDocument(self.document())
        self.setTabStopWidth(self.fontMetrics().width(' ')*2)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        # self.setAcceptRichText(False)

        find = QAction("Find", self)
        find.setShortcut(QKeySequence.Find)
        find.triggered.connect(self.onFindAction)
        find.setShortcutContext(Qt.WidgetShortcut)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._onCustomMenuRequest)
        self.addAction(find)
        self.findw = None
        self.customMenuAction = []
        self.__data = ""
        self._limit_show = False

    def setLimitShow(self, b:bool):
        self._limit_show = b

    def changeLineWarpState(self, sta: bool):
        if sta :
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        else:
            self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def changeShowAction(self, sta: bool):
        log.info(f'changeShowAction {sta}')
        self._limit_show = not sta
        self.setXml(self.__data)

    def copyContent(self):
        if len(self.__data):
            QApplication.clipboard().setText(self.__data)

    def addCustomMenuAction(self, act: QAction):
        self.customMenuAction.append(act)

    def addCustomMenuActions(self, acts: typing.Iterable['QAction']):
        self.customMenuAction.extend(acts)

    def prettyFormat(self):
        try:
            to_ele(self.toPlainText())
            pxml = utils.pretty_xml(self.toPlainText(), True)
            if pxml == self.toPlainText():
                log.debug("no change text.")
                return True, ""
            curs = self.textCursor()
            curs.select(QTextCursor.SelectionType.Document)
            curs.insertText(pxml)
            self.__data = pxml
        except Exception as ex:
            return False, ex
        else:
            return True, ""

    def __updateText(self, text, size):
        self.__data = text
        showtext = text
        if self._limit_show is True:
            ksize = int(size/1024)
            if ksize > 50:
                showtext = text[:10*1024]
                showtext += f"""...\n\n**NOTE**\nThe size of this content is {ksize}KB, only the first 10KB content is displayed!!\nIf you need to see the complete reply, toggle the "Show All Content" action or use the "Copy Content to Clipborad" action to copy the complete content to a separate file."""

        if not self.toPlainText():
            return self.setPlainText(showtext)

        if self.toPlainText() != showtext:
            curs = self.textCursor()
            curs.select(QTextCursor.SelectionType.Document)
            curs.insertText(showtext)
            self.setUpdatesEnabled(True)
            log.debug("end __updateText.")
            return

        log.debug("no change text.")

    def clear(self) -> None:
        self.__data = ""
        return super().clear()

    def setXml(self, xml, try_pretty=True):
        log.debug("Start setxml")
        xml_size = len(xml)
        if not try_pretty:
            return self.__updateText(xml, xml_size)

        try:
            pxml = utils.pretty_xml(xml, True)
        except Exception as ex:
            return self.__updateText(xml, xml_size)
        else:
            log.debug("before to __updateText")
            return self.__updateText(pxml, xml_size)

    def getXml(self, try_pretty=True):
        if not try_pretty:
            return self.__data
        try:
            pxml = utils.pretty_xml(self.__data, True)
        except Exception as ex:
            return self.__data
        else:
            return pxml

    def onFindAction(self):
        log.debug("onFindAction trigred.")
        if not self.findw :
            self.findw = FindDialg(self)
            if len(self.objectName()):
                self.findw.setWindowTitle("Find in %s"%self.objectName())
        self.findw.popUpShow()

    def _onCustomMenuRequest(self, pos: QPoint):
        menu = self.createStandardContextMenu()

        act_find = QAction("&Find", menu)
        act_find.setShortcut(QKeySequence.Find)
        act_find.triggered.connect(self.onFindAction)

        linewarp = QAction("Line Wrap", self)
        linewarp.setCheckable(True)
        linewarp.triggered.connect(self.changeLineWarpState)
        if self.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap:
            linewarp.setChecked(False)
        else:
            linewarp.setChecked(True)

        if not len(self.toPlainText()):
            act_find.setEnabled(False)

        if self.isReadOnly():
            showfull = QAction("Show All Content", menu)
            showfull.setCheckable(True)
            showfull.setChecked(False if self._limit_show is True else True)
            showfull.triggered.connect(self.changeShowAction)

        copycontent = QAction("Copy Content to Clipboard", menu)
        copycontent.triggered.connect(self.copyContent)
        copycontent.setEnabled(True if len(self.__data) else False)

        menu.addSeparator()
        menu.addAction(act_find)
        menu.addAction(copycontent)
        menu.addSeparator()
        menu.addAction(linewarp)
        if self.isReadOnly():
            menu.addAction(showfull)

        if self.customMenuAction:
            menu.addSeparator()
            menu.addActions(self.customMenuAction)

            enable = True if len(self.toPlainText()) else False
            for act in self.customMenuAction:
                act.setEnabled(enable)

        menu.exec(QCursor.pos())
        del menu

class FindDialg(QDialog):
    history_data = SearchHistory()
    history = history_data.searchHistory
    def __init__(self, parent: typing.Union[QTextEdit, QPlainTextEdit], flags = Qt.WindowStaysOnTopHint | Qt.MSWindowsFixedSizeDialogHint | Qt.WindowCloseButtonHint) -> None:
        super().__init__(parent, flags)
        self.editor = parent
        self.setWindowTitle("Find")
        self.setModal(False)

        line_editor = QComboBox(self)
        line_editor.setEditable(True)

        model = QStringListModel(self)
        model.setStringList(self.history)
        line_editor.setModel(model)
        completor = QCompleter(model, self)
        completor.setFilterMode(Qt.MatchFlags() | Qt.MatchContains)
        completor.setCompletionMode(QCompleter.PopupCompletion)
        line_editor.setCompleter(completor)

        view = QListView(self)
        view.setModel(model)
        line_editor.setView(view)
        view.viewport().installEventFilter(self)
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        view.customContextMenuRequested.connect(self._onCustomMenuRequest)

        find_next = QPushButton("Find Next", self)
        find_next.setAutoDefault(True)
        find_next.clicked.connect(self.findtxt)

        bt_cancel = QPushButton("Cancel", self)
        bt_cancel.clicked.connect(self.close)

        mach_whole_word = QCheckBox("Match hole word only", self)
        mach_case = QCheckBox("Match case")
        wrap_around = QCheckBox("Wrap around")
        wrap_around.setChecked(True)

        search_direct = QButtonGroup(self)
        cb_find_up = QRadioButton("Up", self)
        cb_find_down = QRadioButton("Down", self)
        cb_find_down.setChecked(True)
        search_direct.addButton(cb_find_up, 0)
        search_direct.addButton(cb_find_down, 1)

        direct_group = QGroupBox("Direction",self)
        direct_layout = QHBoxLayout()
        direct_layout.addWidget(cb_find_up)
        direct_layout.addWidget(cb_find_down)
        direct_group.setLayout(direct_layout)

        headerlayout = QHBoxLayout()
        headerlayout.addWidget(QLabel("Find what: ", self))

        layout = QHBoxLayout(self)
        layout.setSizeConstraint(QLayout.SetFixedSize)

        headerlayout.addWidget(line_editor, 1)
        # headerlayout.addWidget(find_pre)
        headerlayout.addWidget(find_next)

        col_layout1 = QVBoxLayout()
        col_layout1.addWidget(mach_whole_word)
        col_layout1.addWidget(mach_case)
        col_layout1.addWidget(wrap_around)
        col_layout1.addSpacing(20)
        col_layout1.addStretch(1)

        col_layout2 = QVBoxLayout()
        col_layout2.addWidget(direct_group)
        col_layout2.addStretch(1)

        sub_layout = QHBoxLayout()
        sub_layout.addLayout(col_layout1)
        sub_layout.addLayout(col_layout2)

        fd_layout = QVBoxLayout()
        fd_layout.addLayout(headerlayout)
        fd_layout.addLayout(sub_layout)

        layout.addLayout(fd_layout)

        bt_layout = QVBoxLayout()
        bt_layout.addWidget(find_next)
        bt_layout.addWidget(bt_cancel)
        bt_layout.addStretch(1)
        layout.addLayout(bt_layout)

        self.lineEditor = line_editor
        self.search_direct = search_direct
        self.isWholeWord = mach_whole_word
        self.isMatchCase = mach_case
        self.isWrapAround = wrap_around
        self.view = view
        self.model = model

    def eventFilter(self, a0: QObject, a1: QEvent) -> bool:
        if a1.type() == QEvent.MouseButtonRelease:
            if a1.button() == Qt.RightButton:
                return True
        return super().eventFilter(a0, a1)

    def _onCustomMenuRequest(self):
        menu = QMenu()

        act_del = QAction("Delete", menu)
        act_del.triggered.connect(self._onDeleteHistory)
        act_delall = QAction("Delete All", menu)
        act_delall.triggered.connect(self._onDeleteAllHistory)

        menu.addActions([act_del, act_delall])
        menu.exec(QCursor.pos())
        del menu

        # update current item
        idx = self.view.indexAt(self.view.mapFromGlobal(QCursor.pos()))
        self.view.setCurrentIndex(idx)

    def _onDeleteHistory(self):
        index = self.view.currentIndex()
        txt = self.history[index.row()]
        self.model.removeRow(index.row(), index.parent())
        self.history.remove(txt)

    def _onDeleteAllHistory(self):
        self.lineEditor.clear()
        self.history.clear()

    def popUpShow(self):
        self.lineEditor.clear()
        self.model.setStringList(self.history)
        self.lineEditor.setEditText(self.editor.textCursor().selectedText())
        self.activateWindow()
        self.show()

    def findtxt(self):
        word = self.lineEditor.currentText()
        if not word:
            return
        flag = QTextDocument.FindFlags()
        dir = self.search_direct.checkedId()
        if dir == 0 :
            flag |= QTextDocument.FindFlag.FindBackward

        if self.isMatchCase.isChecked() :
            flag |= QTextDocument.FindFlag.FindCaseSensitively

        if self.isWholeWord.isChecked():
            flag |= QTextDocument.FindFlag.FindWholeWords
        log.debug("Find txt: %s, direct: %s" % (word, dir))
        ret = self.editor.find(word, flag)
        if ret == False and self.isWrapAround.isChecked():
            if dir == 0:
                self.editor.moveCursor(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.MoveAnchor)
            else:
                self.editor.moveCursor(QTextCursor.MoveOperation.Start, QTextCursor.MoveMode.MoveAnchor)

            ret = self.editor.find(word, flag)

        if ret == False:
            QMessageBox.information(self, "Info", '"%s" not found'%word)

        log.debug("find result: %s" % ret)
        self.updateHistory(word)

    def updateHistory(self, txt):
        if not txt:
            return

        for idx, item in enumerate(self.history):
            if txt == item:
                if idx == 0:
                    return
                del(self.history[idx])
        self.history.insert(0, txt)
        if len(self.history) > 30:
            del(self.history[29:])
        self.lineEditor.clear()
        self.lineEditor.model().setStringList(self.history)

        log.debug("history: %s", self.history)

test_xml = """<edit-config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <target>
    <running/>
  </target>
  <config xmlns:xc="urn:ietf:params:xml:ns:netconf:base:1.0">
    <terminal-identify xmlns="urn:rg:params:xml:ns:yang:rg-terminal-identify">
      <template>
        <name>test</name>
        <message-type>
          <lldp xc:operation="remove"/>
        </message-type>
        <sip>
          <address>10.1.1.2</address>
          <port>1020</port>
        </sip>
      </template>
    </terminal-identify>
  </config>
</edit-config>
"""
class XmlEditor(QDialog):
    def __init__(self, xml, title, parent=None, flags=Qt.Window) -> None:
        super().__init__(parent, flags)
        self.setWindowTitle(title)

        editor = XmlEdit(self)
        editor.setXml(xml)

        bt_format = QPushButton("PrettyFormat", self)
        bt_format.clicked.connect(self._onFromatXml)

        bt_cancel = QPushButton("Cancel", self)
        bt_cancel.clicked.connect(self.close)

        bt_ok = QPushButton("OK", self)
        bt_ok.setDefault(True)
        bt_ok.clicked.connect(self._onOk)

        hlayout = QHBoxLayout()
        hlayout.addWidget(bt_format)
        hlayout.addSpacing(300)
        hlayout.addStretch(1)
        hlayout.addWidget(bt_cancel)
        hlayout.addWidget(bt_ok)

        layout = QVBoxLayout(self)
        layout.addWidget(editor, 1)
        layout.addLayout(hlayout)
        self._editor = editor

    def xml(self):
        return self._editor.getXml()

    def _onFromatXml(self):
        ret, estr = self._editor.prettyFormat()
        if ret is False:
            QMessageBox.information(self, "Syntax error ", "syntax error: %s"%estr)
            return False
        return True

    def _onOk(self):
        if self._onFromatXml() is False:
            return;
        self._editor.setXml(self._editor.toPlainText())
        self.accept()

if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d: %(message)s',
                    level=logging.DEBUG)
    app = QApplication([])
    widget = QWidget()
    vlayout = QVBoxLayout(widget)

    editor = XmlEditor(test_xml, "XmlEditor Test")

    vlayout.addWidget(editor)
    widget.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, True)
    widget.show()

    app.exec()