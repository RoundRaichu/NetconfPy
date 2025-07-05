import sys,os,logging
from PyQt5.QtCore import Qt, QFile, QIODevice, QTextStream, QTextCodec
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QApplication, QHBoxLayout, QTabWidget,QFrame, QTextEdit
from PyQt5.QtGui import QPixmap, QFont
from utils import AppInfo

log = logging.getLogger('netconftool.about')

class About(QDialog):
    def __init__(self, parent=None, flags=Qt.Dialog | Qt.WindowCloseButtonHint) -> None:
        super().__init__(parent, flags)
        self.setWindowTitle("About " + QApplication.applicationName())
        mainlayout = QVBoxLayout(self)
        tabwidget = QTabWidget(self)
        mainlayout.addWidget(tabwidget)

        # About TabWidget
        about = QFrame(self)
        about_layout = QVBoxLayout(about)
        tabwidget.addTab(about, "About")

        # logo
        icon = QLabel(self)
        pixmap = QPixmap(':/res/logo.png')
        # pixmap.scaled(64, 64, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        icon.setPixmap(pixmap)
        about_layout.addWidget(icon, 0, Qt.AlignCenter)
        about_layout.addSpacing(10)

        # name
        name = QLabel("NetConf Tool", self)
        f = QFont()
        f.setBold(True)
        name.setFont(f)
        about_layout.addWidget(name, 0, Qt.AlignCenter)
        about_layout.addSpacing(20)
        hashinfo = ""
        build_time = ""
        release_info_f = QFile(':/RELEASE_INFO')
        if release_info_f.open(QIODevice.ReadOnly | QIODevice.Text):
            txt_s = QTextStream(release_info_f)

            line = txt_s.readLine(100)
            while line:
                if "cvs=" in line:
                    hashinfo = line[4:]
                if "btime=" in line:
                    build_time = line[6:]
                line = txt_s.readLine(100)

            log.debug(f'cvs: {hashinfo}, btime={build_time}')

        #version
        about_layout.addWidget(QLabel(f'Version: {AppInfo.currentVerStr()}', self), 0, Qt.AlignCenter)

        #commit
        if len(hashinfo):
            about_layout.addWidget(QLabel(f'Commit: {hashinfo}', self), 0, Qt.AlignCenter)

        #build info
        if len(build_time):
            about_layout.addWidget(QLabel(f'Build: {build_time}', self), 0, Qt.AlignCenter)

        mailto = QLabel(self)
        mailto.setText(
            """<a href="mailto: wangcybest@gmail.com?subject=Issue of NetconfTool&body=What problems are you experiencing?\n\n\nPlease pack the log files in the [%s] directory and send them to me together!">wangcybest@gmail.com</a>""" % AppInfo.logdir())
        mailto.setOpenExternalLinks(True)
        mailto.setCursor(Qt.PointingHandCursor)

        # Issue report
        hlayout = QHBoxLayout()
        hlayout.setContentsMargins(0, 0, 0, 0)
        hlayout.addStretch(1)
        hlayout.addWidget(QLabel("Report Issue: ", self))
        hlayout.addWidget(mailto)
        hlayout.addStretch(1)
        about_layout.addLayout(hlayout, 0)
        about_layout.addSpacing(10)

        # corpyright
        about_layout.addWidget(QLabel(
            "Copyright © 2023 - 2025 "), 0, Qt.AlignCenter)
        about_layout.addStretch(1)
        about_layout.setAlignment(Qt.AlignCenter)

        # History TabWidget
        txtblock = QTextEdit(self)
        txtblock.setReadOnly(True)
        # txtblock.setLineWrapMode(QTextEdit.NoWrap)

        changelog_f = QFile(':/CHANGELOG.txt')
        changelog = 'Unkown'
        if changelog_f.open(QIODevice.ReadOnly | QIODevice.Text):
            txt_s = QTextStream(changelog_f)
            txt_s.setCodec(QTextCodec.codecForName('utf-8'))
            readall = txt_s.readAll()
            if readall :
                changelog = readall
        txtblock.setMarkdown(changelog)
        history = QFrame(self)
        hislayout = QVBoxLayout(history)
        hislayout.addWidget(txtblock)
        tabwidget.addTab(history, "History")

if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d: %(message)s',
                    level=logging.DEBUG)
    app = QApplication(sys.argv)
    widget = About(None)
    widget.show()
    sys.exit(app.exec())
