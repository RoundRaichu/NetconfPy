import typing
import requests
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import os, sys
import logging
from utils import AppInfo

log = logging.getLogger('netconftool.updatecheck')

class VersionUpdate(QObject):
    timestr_format = "yyyy-MM-dd hh:mm:ss.zzz"
    def __init__(self, parent: QObject=None) -> None:
        super().__init__(parent)
        self.lastcheck_dt = QDateTime.fromTime_t(0)
        self.setting_autoCheck = True
        self.needToCheck = True
        self.delayTimer = QTimer()
        self.delayTimer.setSingleShot(True)
        self.delayTimer.timeout.connect(lambda : self.doCheck(False))

        qsetting = QSettings(os.path.join(AppInfo.settingDir(), "setting.ini"), QSettings.IniFormat, self)
        qsetting.beginGroup('update')
         # auto check version
        last_check_datetime = qsetting.value('lastCheckUpdates')
        autoCheckEnable=qsetting.value("autoCheckEnable")
        qsetting.endGroup()

        if autoCheckEnable:
            self.setting_autoCheck = False if autoCheckEnable == 'false' else True

        if last_check_datetime:
            self.lastcheck_dt = QDateTime().fromString(last_check_datetime, VersionUpdate.timestr_format)
            days_pass = self.lastcheck_dt.daysTo(QDateTime.currentDateTime())
            log.info("It has been %d days since the last check", days_pass)
            log.info("last check:%s", self.lastcheck_dt.toString(VersionUpdate.timestr_format))
            if days_pass < 10:
                self.needToCheck = False
    @staticmethod
    def updateUrl():
        if sys.platform == 'cygwin' or sys.platform == 'win32':
            return 'http://172.31.240.44:8080/windows'
        elif sys.platform == 'darwin':
            return 'http://172.31.240.44:8080/macos'
        elif sys.platform == 'linux':
            return 'http://172.31.240.44:8080/linux'

    @staticmethod
    def pkgName(version):
        if sys.platform == 'cygwin' or sys.platform == 'win32':
            if version is None:
                return 'NetConfTool-win-lastest.exe'
            else:
                return 'NetConfTool_Setup_v' + version + '.exe'

        elif sys.platform == 'darwin':
            if version is None:
                return 'NetConfTool-macos-intel-lastest.dmg'
            else:
                return 'NetConfTool_' + version + '_macos-intel.dmg'

        elif sys.platform == 'linux':
            if version is None:
                return 'netconftool-linux-amd64-latest.deb'
            else:
                return 'netconftool_' + version + '_amd64.deb'

    @staticmethod
    def pkgUrl(version=None):
        return VersionUpdate.updateUrl() + '/' + VersionUpdate.pkgName(version)

    def autoCheck(self):
        if self.setting_autoCheck and self.needToCheck and not self.delayTimer.isActive():
            log.info("Start autoCheck timer.")
            self.delayTimer.start(10000)

    def doCheck(self, is_usercall: False):
        log.info("Start do Version Check.")
        qsetting = QSettings(os.path.join(AppInfo.settingDir(), "setting.ini"), QSettings.IniFormat, self)
        qsetting.beginGroup('update')
        qsetting.setValue('lastCheckUpdates', QDateTime.currentDateTime().toString(VersionUpdate.timestr_format))
        qsetting.endGroup()
        ret, msg, new_verstr = self.__doCheck()
        if is_usercall is True :
            if ret is False:
                dlg = UpdateDlg(msg, self.setting_autoCheck, None, None)
            else:
                dlg = UpdateDlg(msg, self.setting_autoCheck, new_verstr, self.getChangeLog())
            dlg.exec()
            self.setting_autoCheck = dlg.autoCheckUpdate
        elif ret == True:
            dlg = UpdateDlg(msg, self.setting_autoCheck, new_verstr, self.getChangeLog())
            dlg.exec()
            self.setting_autoCheck = dlg.autoCheckUpdate

    def __doCheck(self):
        cv_list = AppInfo.currentVerCode()
        try:
            url = self.updateUrl() + '/LATEST.TXT'
            log.info("Update Check url:%s" % url)
            resp = requests.get(url, timeout=2)
            resp.encoding = 'UTF-8'
            if resp.status_code != 200:
                return False, 'Server connection failure'

            log.info("Server latest version: %s", resp.text)
            rv_list = resp.text.split('.')
            for i in range(len(rv_list)):
                if int(cv_list[i]) < int(rv_list[i]):
                    return True, 'New version available - %s'%resp.text, resp.text

            return False, 'There are currently no updates available.', ''

        except Exception as e:
            return False, 'Server connection failure', ''

    def getChangeLog(self):
        try:
            url = self.updateUrl() + '/CHANGELOG.txt'
            resp = requests.get(url, timeout=2)
            resp.encoding = 'UTF-8'
            if resp.status_code != 200:
                return 'Server connection failure, status code:%d'%resp.status_code
            log.debug("Server CHANGELOG.txt: %s", resp.text)
            return resp.text
        except Exception as e:
            return 'Server connection failure'

class UpdateDlg(QDialog):
    def __init__(self, msg, autocheck: bool, newver=None, changelog=None, parent=None, flags=Qt.Dialog | Qt.WindowCloseButtonHint) -> None:
        super().__init__(parent, flags)
        self.setWindowTitle("Check Updates")
        # self.setWindowModality(Qt.WindowModal)
        vlayout = QVBoxLayout(self)

        current_version = QLabel("You are using: %s\n"%AppInfo.currentVerStr(), self)
        vlayout.addWidget(current_version)

        info = QLabel(self)
        info.setText(msg)
        vlayout.addWidget(info)

        if changelog:
            bt_act = QPushButton("Download Now", self)
            bt_act.clicked.connect(self.goDownload)
            changelog_edit = QTextEdit(self)
            changelog_edit.setReadOnly(True)
            changelog_edit.setMarkdown(changelog)
            vlayout.addWidget(changelog_edit, 10)
        else:
            vlayout.addSpacing(50)
            vlayout.addStretch(1)
            bt_act = QPushButton("OK", self)
            bt_act.clicked.connect(self.close)

        bt_act.setDefault(True)
        cb_auto = QCheckBox("Automatically check for updates")
        cb_auto.setChecked(autocheck)
        cb_auto.stateChanged.connect(self._onChangeAutoCheck)

        process_bar = QProgressBar(self)
        process_bar.setHidden(True)
        process_bar.setFixedWidth(200)

        save_to_name = VersionUpdate.pkgName(newver)
        url = VersionUpdate.pkgUrl()
        log.debug("pkg url: %s", url)

        save_filepath = os.path.join(QStandardPaths.standardLocations(QStandardPaths.DownloadLocation)[0], save_to_name)
        work = DownloadPackage(url, save_filepath)
        work.total.connect(process_bar.setMaximum)
        work.compelete.connect(process_bar.setValue)
        work.done.connect(self.finishedDownload)
        work.msg.connect(lambda str: QMessageBox.information(self, 'Info', str))

        thread = QThread()
        thread.started.connect(work.download)
        # thread.finished.connect(thread.deleteLater)
        work.moveToThread(thread)

        hlayout = QHBoxLayout()
        hlayout.addWidget(cb_auto)
        hlayout.addStretch(1)
        hlayout.addSpacing(200)
        hlayout.addWidget(process_bar, 2)
        hlayout.addWidget(bt_act)
        vlayout.addLayout(hlayout)

        self.cb_auto = cb_auto
        self.process_bar = process_bar
        self.thrd = thread
        self.work = work

    def goDownload(self, ver:str):
        # QDesktopServices.openUrl(QUrl(VersionUpdate.updateUrl()))
        if self.thrd.isRunning():
            return
        self.thrd.start()
        self.process_bar.setValue(0)
        self.process_bar.setHidden(False)

    def finishedDownload(self, savefile: str):
        self.process_bar.setHidden(True)
        log.info("Download finished!, save to : %s", savefile)
        if len(savefile) == 0:
            self.thrd.quit()
            return self.thrd.wait()

        result = QMessageBox.question(self, "Install Updates", "The new version has been downloaded. Update now?",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        url = savefile if result == QMessageBox.Yes else os.path.dirname(savefile)
        QDesktopServices.openUrl(QUrl.fromLocalFile(url));
        self.close()


    def _onChangeAutoCheck(self, sta):
        qsetting = QSettings(os.path.join(AppInfo.settingDir(), "setting.ini"), QSettings.IniFormat, self)
        qsetting.beginGroup('update')
         # auto check version
        qsetting.setValue('autoCheckEnable', True if sta == Qt.Checked else False)
        qsetting.endGroup()

    def closeEvent(self, a0: QCloseEvent) -> None:
        log.info("UpdateDlg closed!")
        self.work.stop()
        self.thrd.quit()
        self.thrd.wait()
        self.work.deleteLater()
        return super().closeEvent(a0)

    @property
    def autoCheckUpdate(self):
        sta = self.cb_auto.checkState()
        return True if sta == Qt.Checked else False

class DownloadPackage(QObject):
    total = pyqtSignal(int)
    compelete = pyqtSignal(int)
    done = pyqtSignal(str)
    msg = pyqtSignal(str)
    def __init__(self, url, to_file, parent=None) -> None:
        super().__init__(parent)
        self.url = url
        self.savefile = to_file
        self.run = True

    def download(self):
        self.run = True
        log.info("Start download updates, url:%s, to:%s", self.url, self.savefile)
        download_size = 0
        try:
            resp = requests.get(self.url, timeout=10, verify=False, stream=True)
            size = int(resp.headers.get('content-length', '0'))
            self.total.emit(size)
            with open(self.savefile, "wb") as file:
                for data in resp.iter_content(chunk_size=1024*256):   # 每取满chunk_size字节即存储
                    file.write(data)
                    download_size += len(data)
                    log.debug("Download: %s%%", download_size/size * 100)
                    self.compelete.emit(download_size)
                    if self.run == False:
                        log.info("worker stoped.")
                        return self.done.emit("")
                    QApplication.processEvents()
            self.done.emit(self.savefile)
        except Exception as ex:
            self.done.emit("")
            log.info("Download Fail: %s", str(ex))
            self.msg.emit("Download Fail.")

    def stop(self):
        self.run = False

if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QCoreApplication

    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d: %(message)s',
                    level=logging.DEBUG)
    QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication([])
    dpi = app.primaryScreen().logicalDotsPerInch()
    factor = 1
    if dpi > 100.0:
        factor = dpi/96
        font = app.font()
        font.setPixelSize(12 * factor)
        app.setFont(font)

    vupdate= VersionUpdate(None)
    vupdate.doCheck(True)
    app.exec()