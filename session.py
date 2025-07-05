import os
import socket
import time
import typing
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import QWidget
from ncclient import manager
from ncclient.operations import RPC, RaiseMode
from ncclient.operations.errors import MissingCapabilityError, OperationError
from ncclient.devices.default import DefaultDeviceHandler
from ncclient.transport.notify import NotificationM
from ncclient.xml_ import *
from device_manage import *
from xmleditor import XmlEdit, FindDialg
from threading import Thread, Event
from utils import pretty_xml, millsecondToStr
import logging
from session_history import SessionHistoryWidget, SessionOperType

log = logging.getLogger('netconftool.session')

class UndefinedDeviceHandler(DefaultDeviceHandler):
    """
    Undefined handler for device specific information.

    In the device_params dictionary, which is passed to __init__, you can specify
    the parameter "ssh_subsystem_name". That allows you to configure the preferred
    SSH subsystem name that should be tried on your Undefined switch. If connecting with
    that name fails, or you didn't specify that name, the other known subsystem names
    will be tried. However, if you specify it then this name will be tried first.

    """
    _EXEMPT_ERRORS = []

    def __init__(self, device_params):
        super(UndefinedDeviceHandler, self).__init__(device_params)

    def get_xml_base_namespace_dict(self):
        return {None: BASE_NS_1_0}

    def get_xml_extra_prefix_kwargs(self):
        d = {}
        d.update(self.get_xml_base_namespace_dict())
        return {"nsmap": d}

def datastore_or_url(wha, loc, capcheck=None):
    node = etree.Element(wha)
    if "://" in loc: # e.g. http://, file://, ftp://
        if capcheck is not None:
            capcheck(":url") # url schema check at some point!
            etree.SubElement(node, "url").text = loc
    else:
        etree.SubElement(node, loc)
    return node

class _NccProxSignal(QObject):
    connectInfoChanged = pyqtSignal(str)
    notificationRecvied = pyqtSignal(str)
    connectionStatusChanged = pyqtSignal(bool)
    errorNoitfy = pyqtSignal(str)

class NccProxy(Thread, QObject):

    def __init__(self, config: dict):
        log.debug("NccProxy __init__")
        Thread.__init__(self)
        QObject.__init__(self)
        self._cfg = config
        self.setDaemon(True)
        self.__runing = Event()
        self.__connect = Event()
        self._is_connected = False
        self.__connect.clear()
        self.signals = _NccProxSignal()
        self.__runing.set()
        self.__abort_wait = Event()
        self.__abort_wait.clear()
        self._manager = None
        self.start()

    def __del__(self):
        log.debug("NccProxy __del__")
        self.__runing.clear()

    def __exit__(self, *args):
        log.debug("NccProxy __exit__")
        self.__runing.clear()

    def _setConnectState(self, sta: bool):
        if self._is_connected != sta:
            log.debug("NccProxy _setConnectState, %s session-id: %s", sta, self._manager.session_id)
            self._is_connected = sta
            self.signals.connectionStatusChanged.emit(sta)

    def run(self):
        try:
            while self.__runing.is_set():
                # log.debug("NccProxy threading running!", self.name, self.native_id)
                if not self.__connect.is_set():
                    self.__connect.wait()
                    if self._manager:
                        log.info("Is callhome session, run direct...")
                        self._setConnectState(True)
                        continue

                    log.info("NccProxy start connect: %s!", self.connect_info)
                    try:
                        cfg = self._cfg
                        self._manager = manager.connect_ssh(host=cfg["host"], port=cfg["port"],
                                                            username=cfg["user"], password=cfg["passwd"],
                                                            hostkey_verify=False, timeout=60, keepalive=60,
                                                            device_params={'handler':UndefinedDeviceHandler})
                        self._manager.timeout = cfg.get('timeout', 60)
                        self._manager.raise_mode = RaiseMode.NONE
                        self._manager.async_mode = True
                        self._manager.huge_tree = True
                    except Exception as e:
                        log.info("NccProxy connect[%s] failed: %s",  self.connect_info, str(e))
                        self.__connect.clear()
                        self._setConnectState(False)
                        self.signals.errorNoitfy.emit("Connect failed: " + str(e))
                    else:
                        log.info("NccProxy connect succ: %s", self.connect_info)
                        self._setConnectState(True)
                else:
                    if self._manager.connected:
                        ntf = self._manager.take_notification(block=True, timeout=1)
                        if ntf != None:
                            self.signals.notificationRecvied.emit(ntf.notification_xml)
                    else:
                        log.info("NccProxy connect is lost: %s!", self.connect_info)
                        self._setConnectState(False)
                        self.__connect.clear()
                        if self._manager:
                            del self._manager
                            self._manager = None
            # thread end
            log.info("NccProxy close session: %s", self.connect_info)
            if self._manager.connected:
                self._manager.close_session()
            self._setConnectState(False)
            self.__connect.clear()
            del self._manager
            self._manager = None

        except Exception as e:
            self.signals.errorNoitfy.emit(str(e))
            self.close()

    def setManager(self, mgr):
        if mgr.connected:
            self._manager = mgr

    @property
    def connect_info(self) -> str:
        return str('%s@%s:%d'%(self._cfg.get('user', '-'), self._cfg.get('host', '-'), self._cfg.get('port', '-')))

    @property
    def manager(self):
        return self._manager

    @property
    def is_connected(self):
        return self._is_connected

    def connect(self):
        self.__connect.set()

    def disconnect(self):
        log.info("NccProxy close session!")
        self._manager.close_session()

    def close(self):
        self.__runing.clear()

    def reqAbort(self):
        self.__abort_wait.set()

    def _waitAsyncRPCReply(self, rpc: RPC):
        loop = QEventLoop(self)
        start_time = time.time()
        end_time = start_time + self._cfg.get('timeout', 60)
        self.__abort_wait.clear()
        while not self.__abort_wait.is_set() and not rpc.event.isSet() and end_time > time.time():
            if not loop.processEvents():
                rpc.event.wait(0.01)

        if self.__abort_wait.is_set():
            raise UserWarning("User canceled the operation")

        if rpc.event.isSet():
            log.info("NccProxy rpc.event is set.")
            if rpc.error:
                raise rpc.error
            else:
                return rpc.reply
        else:
            raise TimeoutError('Waiting for RPC reply timeout')

    # def rpc(self, rpc_command, source=None, filter=None, config=None, target=None, format=None):
    #     rpc, req = self._manager.rpc(rpc_command, source, filter, config, target, format)
    #     return self._waitAsyncRPCReply(rpc)

    def dispatch(self, rpc_command, source=None, filter=None):
        rpc, req = self._manager.dispatch(rpc_command, source, filter)
        # return self._waitAsyncRPCReply(rpc), req
        return rpc, req

    def get_schema(self, identifier, version=None, format=None):
        rpc, req = self._manager.get_schema(identifier, version, format)
        # return self._waitAsyncRPCReply(rpc), req
        return rpc, req

    def get(self, filter=None, with_defaults=None):
        rpc, req = self._manager.get(filter, with_defaults)
        # return self._waitAsyncRPCReply(rpc), req
        return rpc, req

    def wait_asnync_reply(self, rpc):
        return self._waitAsyncRPCReply(rpc)

class QCallHome(QObject):
    info = pyqtSignal(str)
    done = pyqtSignal(bool)
    def __init__(self, *args, **kwds) -> None:
        super().__init__(parent=None)
        self.args = args
        self.kwds = kwds
        self.run = True
        self.mgr = None
        self.raddr = None

    def __del__(self):
        log.info("QCallHome __del__")

    def doCallhome(self):
        kwds = self.kwds
        args = self.args
        port = kwds.get("port",4334)
        listen_sockets =[]

        for fa in [socket.AF_INET, socket.AF_INET6]:
            try:
                srvsock = socket.socket(fa, socket.SOCK_STREAM, socket.IPPROTO_TCP)
                srvsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if fa == socket.AF_INET6 and sys.platform != "win32":
                    srvsock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                if sys.platform != "win32":
                    srvsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                srvsock.bind(('', port))
                srvsock.settimeout(0.3)
                srvsock.listen()
                listen_sockets.append(srvsock)
            except Exception as ex:
                self.info.emit("Port %s listen failed. %s"%(port, str(ex)))

        ret = False
        if not len(listen_sockets):
            self.done.emit(ret)
            self.info.emit('No Port listening success. Stop!')
            return
        else:
            self.info.emit("Start Listening in all IPv4/IPv6 address on port %d."%port)

        self.run = True
        while self.run:
            for srv_socket in listen_sockets:
                if not self.run:
                    break
                try:
                    # laddr = srv_socket.getsockname()
                    log.debug("Callhome going accept %s, port: %d", srv_socket, port)
                    # self.info.emit("Listening on port: %s"%(laddr[1]))
                    sock, remote_host = srv_socket.accept()
                except Exception as ex:
                    log.debug(str(ex))
                    # break
                else:
                    self.info.emit('Callhome connection initiated from remote host {0}'.format(remote_host))
                    kwds['sock'] = sock
                    try:
                        self.mgr = manager.connect_ssh(*args, **kwds)
                        self.mgr.timeout = kwds.get('timeout', 60)
                        self.mgr.raise_mode = RaiseMode.NONE
                        self.mgr.async_mode = True
                        self.mgr.huge_tree = True
                    except Exception as ex:
                        self.info.emit("Callhome connect ssh fail. %s"%str(ex))
                        # listen_sockets.remove(srv_socket)
                        # break
                    else:
                        self.info.emit("Callhome session connected: %s"%sock)
                        self.raddr = sock.getpeername()
                        ret = True
                        break

            if ret == True or len(listen_sockets) == 0:
                break

        for srvk in listen_sockets:
            log.info("Stop listen %s", srvk)
            srvk.close()

        self.done.emit(ret)

    def stopWorker(self):
        log.info("Stop listening...")
        self.run = False

class CallHomeDialog(QDialog):
    def __init__(self, cfg={}, parent=None, flags=Qt.WindowCloseButtonHint) -> None:
        super().__init__(parent, flags)
        self.setWindowTitle("Listening for Call Home Connections...")

        wait_label = QLabel(self)
        pixmap = QPixmap(':/res/wait.png')
        wait_label.setPixmap(pixmap.scaled(32, 32, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))

        took_sec = QLabel("0 s", self)

        bt_stop = QPushButton("Cancel", self)
        bt_stop.clicked.connect(self.close)

        info_label = QLabel("Waiting...", self)
        log_widget = QPlainTextEdit(self)
        log_widget.setReadOnly(True)
        log_widget.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        blayout = QHBoxLayout()
        blayout.addStretch(1)
        blayout.addSpacing(500)
        blayout.addWidget(bt_stop)

        layout = QVBoxLayout(self)
        # layout.setSizeConstraint(QLayout.SetFixedSize)
        layout.addWidget(wait_label, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(took_sec, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(20)
        layout.addWidget(info_label)
        layout.addWidget(log_widget)
        layout.addLayout(blayout)

        worker = QCallHome(host=cfg.get('host', ''),
                           port=cfg.get('port', 4334),
                           username=cfg.get('user', 'unkown'),
                           password=cfg.get('passwd', 'unkown'),
                           hostkey_verify=False,
                           timeout=cfg.get('timeout', 60),
                           keepalive=60,
                           device_params={'handler':UndefinedDeviceHandler})
        info_label.setText("Listening on port: %d" %cfg.get('port', 4334))
        worker.done.connect(self.callDone)
        worker.info.connect(self._appendLog)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.doCallhome)
        thread.finished.connect(thread.deleteLater)
        log.info("before start thread.")
        thread.start()
        log.info("end start thread.")

        timer = QTimer()
        timer.setInterval(1000)
        timer.timeout.connect(self.updateTimerShow)
        timer.start()

        self.thrd = thread
        self.worker = worker
        self.bt_stop = bt_stop
        self.tookSeconds = took_sec
        self.timer = timer
        self.tooksec = 0
        self.info = info_label
        self.log_widget = log_widget

    def __del__(self):
        log.info("CallHomeDialog __del__")
        self.worker.stopWorker()
        self.thrd.quit()
        self.thrd.wait()
        self.worker.deleteLater()

    def _appendLog(self, log, datetime = None):
        if datetime:
            dt = datetime
        else:
            dt = QDateTime.currentDateTime()
        log = "[" + dt.toString("yyyy-MM-dd hh:mm:ss.zzz") + "] " + log
        self.log_widget.appendPlainText(log)

    def updateTimerShow(self):
        self.tooksec += 1
        self.tookSeconds.setText('%d s'%self.tooksec)

    def callDone(self, ret: bool):
        log.info("CallHomeDialog receive done, %s", ret)
        self.timer.stop()
        if ret:
            log.info("accept accept")
            return self.accept()
        self.info.setText("Warning: No Port listening success. Stop!")

    def closeEvent(self, a0: QCloseEvent) -> None:
        log.info("CallHomeDialog close.")
        self.worker.stopWorker()
        self.thrd.quit()
        self.thrd.wait()
        self.worker.deleteLater()
        self.deleteLater()
        return super().closeEvent(a0)



class _NetconfToolSignals(QObject):
    connectInfoChanged = pyqtSignal(str)
    connectionStatusChange = pyqtSignal(bool)
    sendXmlNotify = pyqtSignal(str)
    sessionOperableChanged = pyqtSignal(bool)

default_xml = """
<get xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
<filter type="subtree">
<DeviceManagement xmlns="urn:rg:params:xml:ns:yang:rg-device-management">
<DeviceInfo/>
</DeviceManagement>
</filter>
</get>"""


class NetconfSession(QWidget):
    def __init__(self, cfg={}, parent=None, flags=Qt.WindowType.Widget) -> None:
        super().__init__(parent, flags)
        log.debug("NetconfSession __init__")
        self._connectInfo = "%s@%s:%d" % (cfg["user"], cfg["host"], cfg["port"])
        self._conf_data = cfg
        self._is_connected = False
        self._proxy = NccProxy(cfg)
        self.signals = _NetconfToolSignals()
        self._capshow = None
        self._schemashow = None
        self._schemas = []
        self.initUI()
        self._proxy.signals.notificationRecvied.connect(self._onRecveNotification)
        self._proxy.signals.errorNoitfy.connect(self._msgBox)
        self._proxy.signals.connectionStatusChanged.connect(self._onDeviceConnectStatusChanged)
        self._widgetCgroupCtrl(False)
        self.raddr = None  #保存Call home的远端链接信息
        self.reconnectTimer = QTimer(self)
        self.reconnectTimer.setSingleShot(True)
        self.reconnectTimer.timeout.connect(self._reconnect)
        self.sessionOperable = False
        self._displayName = ""
        self._datastoreLock = {}

    def __del__(self):
        log.debug("NetconfSession __del__")
        self._proxy.close()

    def __exit__(self):
        log.debug("NetconfSession __exit__")
        self._proxy.close()

    def _assert(self, capability):
        if self._proxy is None or self._proxy.manager is None:
            return
        """Subclasses can use this method to verify that a capability is available with the NETCONF
        server, before making a request that requires it. A :exc:`MissingCapabilityError` will be
        raised if the capability is not available."""
        if capability not in self._proxy.manager.server_capabilities:
            raise MissingCapabilityError('Server does not support [%s]' % capability)

    def serverHaveCapability(self, capability):
        if self._proxy is None or self._proxy.manager is None:
            return False
        if capability in self._proxy.manager.server_capabilities:
            return True
        return False

    def initUI(self):
        splitter = QSplitter(Qt.Orientation.Vertical, self)
        splitter.setHandleWidth(0)
        # splitter.setContentsMargins(5, 5, 5, 5)

        # Command XML
        group_send = QFrame(self)
        splitter.addWidget(group_send)

        l_send = QVBoxLayout(group_send)
        l_send.addWidget(QLabel("Command XML", self))
        self._command = XmlEdit(self, 'Command XML')
        self._command.setXml(default_xml)
        l_send.addWidget(self._command)

        self._bt_send = QPushButton(QIcon(':/res/sent.png'), "Send", self)
        self._bt_send.clicked.connect(self._sendXml)

        self._bt_abort = QPushButton("Abort", self)
        self._bt_abort.setEnabled(False)
        self._bt_abort.clicked.connect(self._onBtAbort)

        self._bt_autosave = QCheckBox("Auto Save")
        self._bt_autosave.setChecked(True)
        self._bt_autosave.setToolTip("Auto save xml to history")

        h_layout = QHBoxLayout()
        # h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.addWidget(self._bt_send)
        h_layout.addWidget(self._bt_abort)
        h_layout.addStretch(1)
        h_layout.addWidget(self._bt_autosave)
        l_send.addLayout(h_layout)

        # RPC Reply
        self._rawReply = XmlEdit(self, 'Reply')
        act_clear = QAction("Clear", self)
        act_clear.triggered.connect(self._rawReply.clear)
        self._rawReply.addCustomMenuAction(act_clear)
        self._rawReply.setReadOnly(True)
        self._rawReply.setLimitShow(True)

        cap = CapabilityWidgets([], self)
        cap.layout().setContentsMargins(0, 0, 0, 0)
        self._capability = cap

        out = QTabWidget(self)
        out.setDocumentMode(True if sys.platform == 'darwin' else False)
        out.insertTab(0, self._rawReply, "Reply")
        out.insertTab(1, cap, "Capabilities")
        self._output = out

        response_group = QFrame(self)
        l_resp = QVBoxLayout(response_group)
        l_resp.setContentsMargins(0, 0, 0, 0)
        l_resp.addSpacing(5)
        l_resp.addWidget(out)
        splitter.addWidget(response_group)

        self._log = QPlainTextEdit(self)
        if sys.platform == 'darwin':
            font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        else:
            font = QFont("Consolas")
        self._log.setFont(font)
        self._log.setReadOnly(True)

        self._notification = NotificationWidget(self)
        self._notification.signal.countChanged.connect(self._onNotificationCountChagned)

        self._sessionHistory = SessionHistoryWidget(self)

        other_group = QFrame(self)
        l_other = QVBoxLayout(other_group)
        l_other.setContentsMargins(0, 0, 0, 0)
        other = QTabWidget(self)
        other.setDocumentMode(True if sys.platform == 'darwin' else False)
        other.insertTab(0, self._log, "Log")
        other.insertTab(1, self._notification, "Notifications")
        other.insertTab(2, self._sessionHistory, "Session History")

        self._other = other
        l_other.addSpacing(5)
        l_other.addWidget(other)

        splitter.addWidget(other_group)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)
        layout.setContentsMargins(0, 0, 0, 0)

        if not sys.platform == 'darwin':
            for frame in [group_send, response_group, other_group]:
                frame.setFrameShape(QFrame.Shape.Box)
                frame.setLineWidth(0)
                frame.setFrameShadow(QFrame.Shadow.Sunken)
            group_send.setLineWidth(1)

        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    @property
    def options(self) -> dict:
        return self._conf_data

    def setManager(self, mgr, raddr):
        self.raddr = raddr
        return self._proxy.setManager(mgr)

    def setOptions(self, option: dict):
        self._conf_data = option

    def update_response(self, xml):
        self._rawReply.setXml(xml)
        self._output.setCurrentWidget(self._rawReply)

    def _appendLog_RPCErrorDetail(self, errors, logtime):
        for err in errors:
            if err.type:
                self._appendLog(f"  Error type: {err.type}", datetime=logtime,
                                fcolor=Qt.GlobalColor.darkRed, newline=False)
            if err.tag:
                self._appendLog(f"  Error tag: {err.tag}", datetime=logtime,
                                fcolor=Qt.GlobalColor.darkRed, newline=False)
            if err.app_tag:
                self._appendLog(f"  Error app_tag: {err.app_tag}", datetime=logtime,
                                fcolor=Qt.GlobalColor.darkRed, newline=False)
            if err.severity:
                self._appendLog(f"  Error severity: {err.severity}", datetime=logtime,
                                fcolor=Qt.GlobalColor.darkRed, newline=False)
            # if err.info:
            #     self._appendLog(f"  Error info: {err.info}", datetime=logtime,
            #                     fcolor=Qt.GlobalColor.darkRed, newline=False)
            if err.path:
                self._appendLog(f"  Error path: {err.path}", datetime=logtime,
                                fcolor=Qt.GlobalColor.darkRed, newline=False)
            if err.message:
                self._appendLog(f"  Error message: {err.message}", datetime=logtime,
                                fcolor=Qt.GlobalColor.darkRed, newline=False)

    def _sendXml(self):
        if not self.sessionOperable:
            log.info('Session is not operable now.')
            return None

        try:
            rpc = to_ele(self._command.toPlainText())
        except Exception as ex:
            self._msgBox("XML parse error: %s" % (str(ex)))
            return;

        try:
            log.info("etree.Qname(rpc).localname: %s", etree.QName(rpc).localname)
            # 清理只包含空格和换行内容的xml节点，RF4741规定节点必须包含非空白字符
            for elem in rpc.iter():
                if elem.text and all(char.isspace() for char in elem.text) is True:
                    elem.text = None

            if etree.QName(rpc).localname == 'rpc':
                for child in rpc:
                    new_rpc = child
                rpc = new_rpc
            oper = etree.QName(rpc).localname
            # 锁状态特殊处理
            if oper in ['lock','unlock']:
                for tg in etree.ElementDepthFirstIterator(rpc):
                    lockOpTarget = etree.QName(tg).localname

            # 更新 Command XML，记录Command History
            sendxml = to_xml(rpc, pretty_print=True)
            self._command.setXml(sendxml)
            if self._bt_autosave.isChecked():
                self.signals.sendXmlNotify.emit(sendxml)

            # 阻止发送新的请求，这里不立即控制UI状态，而是在300ms后启动UI状态切换, 避免UI闪动
            self.sessionOperable = False
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(self.cgroupCtrlDelay)
            timer.start(300)
            # 请求发送RPC
            rpc_obj, req = self._proxy.dispatch(rpc)

            real_rpc = to_ele(req)
            msgid = real_rpc.get("message-id")
            msg_id = f'message-id="{msgid}"' if msgid is not None else ""

            # 这里记录的send time只是发送请求的时间，和实际发送时间有偏差，只用于日志显示
            send_time = QDateTime.currentDateTime()
            self._appendLog(f"RPC <{oper}> request to send, {msg_id}.", send_time)
            self._sessionHistory.appendHistory(send_time, SessionOperType.Out, req)
            # 等待应答
            self._rawReply.clear()
            resp = self._proxy.wait_asnync_reply(rpc_obj)
            # 记录当前时间，用于日志显示
            cur_time = QDateTime.currentDateTime()

            # 获取真实时间戳，计算真实耗时
            timediff = self._proxy._manager.get_tooktime(msgid)
            if timediff == 0:
                log.info(f"Get real timestamp fail!")
                timediff = send_time.msecsTo(cur_time)
            # 转换成 xx hr xx min xx sec yy ms的形式
            took_str = millsecondToStr(timediff)

            self.update_response(resp.xml)

            if resp.error:
                self._appendLog(f"Command <{oper}> was unsuccessful, {msg_id}. RPC error was reported:",
                                cur_time, fcolor=Qt.GlobalColor.darkRed, newline=False)
                self._appendLog_RPCErrorDetail(resp.errors, cur_time)
            else:
                self._appendLog(f"Command <{oper}> was successful, {msg_id} (took {took_str}).",
                                cur_time, fcolor=Qt.GlobalColor.darkGreen, newline=False)
            self._sessionHistory.appendHistory(cur_time, SessionOperType.In, resp.xml, extra=f'(took {took_str})')
            # 释放UI控制
            self._bt_abort.setEnabled(False)
            self._widgetCgroupCtrl(True)

            # 锁状态特殊处理
            if oper in ['lock','unlock']:
                opstate = True if resp.ok else False
                if opstate :
                    lockstate = True if oper == 'lock' else False
                    log.info("set %s lockstate %s", lockOpTarget, lockstate)
                    self._datastoreLock[lockOpTarget] = lockstate

            # 做一个UTF-8字符检查
            if resp.non_utf8_tags:
                self._appendLog("Warning: The reply contains non UTF-8 characters!", cur_time,
                                fcolor=Qt.GlobalColor.darkMagenta)
                for tag in resp.non_utf8_tags:
                    for line in str(pretty_xml(tag)).split('\n'):
                        self._appendLog(f"  {line}", cur_time, fcolor=Qt.GlobalColor.darkMagenta, newline=False)

            return resp
        except Exception as e:
            cur_time = QDateTime.currentDateTime()
            self._appendLog(f"Command <{oper}> was unsuccessful, {msg_id}. ({str(e)})",
                            cur_time, fcolor=Qt.GlobalColor.darkRed, newline=False)
            self._bt_abort.setEnabled(False)
            self._widgetCgroupCtrl(True)

    def cgroupCtrlDelay(self):
        self._widgetCgroupCtrl(False)
        self._bt_abort.setEnabled(True)

    def setCommandXML(self, cxml, execute=False):
        if not len(cxml):
            return

        if not self.sessionOperable:
            log.info('Session is not operable now.')
            return

        self._command.setXml(cxml)
        if execute:
            return self._sendXml()

    def _appendLog(self, logstr, datetime = None, fcolor=Qt.GlobalColor.black, newline=True):
        if datetime:
            dt = datetime
        else:
            dt = QDateTime.currentDateTime()
        timestamp = f"[{dt.toString('yyyy-MM-dd hh:mm:ss.zzz')}] "
        log.info(logstr)
        self._log.appendPlainText("")

        last = self._log.document().lastBlock()
        cursor = QTextCursor(last)
        cursor.beginEditBlock()
        fmt = self._log.currentCharFormat()
        fmt.setForeground(QBrush(QColor(Qt.GlobalColor.gray)))
        fmt.setFontItalic(True)
        cursor.insertText(timestamp, fmt)
        if newline is True:
            self._log.appendPlainText("")
            cursor = QTextCursor(self._log.document().lastBlock())
            cursor.insertText(timestamp, fmt)
        fmt.setFontItalic(False)

        if len(logstr):
            fmt.setForeground(QBrush(QColor(fcolor)))
            cursor.insertText(logstr, fmt)

        cursor.endEditBlock()

    def _onRecveNotification(self, ntf):
        dt = QDateTime.currentDateTime()
        ntf = NotificationM(ntf)
        self._appendLog(f"Received a notification <{ntf.notifcaiton_name}>.", dt, fcolor=Qt.GlobalColor.darkYellow)
        self._notification.appendNotification(dt, ntf)
        self._sessionHistory.appendHistory(dt, SessionOperType.In, ntf.notification_xml)

    def _onNotificationCountChagned(self, count: int):
        if count == 0 :
            self._other.setTabText(1, "Notifications")
        else:
            self._other.setTabText(1, "Notifications (%d)" % count)

    def _clearConnectionsSensitiveData(self):
        """清除会话连接断开后需要清理的数据"""
        self._datastoreLock.clear()
        if self._capshow:
            del self._capshow
            self._capshow = None
        if self._schemashow:
            del self._schemashow
            self._schemashow = None
            del self._schemas
            self._schemas = []

    def _onDeviceConnectStatusChanged(self, sta):
        self._widgetCgroupCtrl(sta)
        cur_datetime = QDateTime.currentDateTime()
        if sta:
            msg = "Session connected."
            cfg = self._conf_data
            self._connectInfo = "%s@%s:%d" % (cfg["user"], cfg["host"], cfg["port"])
            if self._proxy.manager:
                self._capability.updateCapability(self._proxy.manager.server_capabilities)
            else:
                log.error(f"self._proxy.manager is {self._proxy.manager}")
            self._appendLog(msg, cur_datetime, Qt.GlobalColor.blue)
        else:
            self._clearConnectionsSensitiveData()
            if self._userDisconnet == False:
                if self._conf_data.get('auto-reconnect', False):
                    msg = "Session was terminated unexpectedly and will be reconnected in 60 seconds."
                    self.reconnectTimer.start(60*1000)
                else:
                    msg = "Session was terminated unexpectedly."
                self._appendLog(msg, cur_datetime, Qt.GlobalColor.red)
            else:
                msg = "Session was terminated successfully."
                self._appendLog(msg, cur_datetime, Qt.GlobalColor.blue)

        detail_msg = "Connected to " if sta else "Disconnected from "
        detail_msg += self._connectInfo
        if not sta:
            detail_msg += f"\n{msg}"
        self._sessionHistory.appendHistory(cur_datetime, SessionOperType.Session, detail_msg,
                                           "Connected" if sta else "Disconnected")
        self.signals.connectionStatusChange.emit(sta)

    def _widgetCgroupCtrl(self, sta: bool):
        self.sessionOperable = sta
        self.signals.sessionOperableChanged.emit(sta)
        self._bt_send.setEnabled(sta)
        if sta == False:
            self._bt_abort.setEnabled(False)

    def _msgBox(self, text):
        self._appendLog(text, fcolor=Qt.red)
        QMessageBox.warning(self, "Warning", text, QMessageBox.Ok)

    def closeEvent(self, ev: QCloseEvent):
        self._proxy.close()

    def connect(self, is_reconnect = False):
        if not self._proxy.is_connected:
            msg = "Reconnecting" if is_reconnect else "Connecting"
            self._appendLog(f"{msg} to {self.connectInfoStr}...")
        self.reconnectTimer.stop()
        self._userDisconnet = False
        self._proxy.connect()

    def _reconnect(self):
        self.connect(is_reconnect = True)

    def disconnect(self):
        self._appendLog(f"Disconnecting {self.connectInfoStr}...")
        self._proxy.disconnect()
        self._userDisconnet = True

    def _onBtAbort(self):
        return self._proxy.reqAbort()

    def onActDiscardChanges(self):
        try:
            self._assert(':candidate')
        except Exception as ex:
            return QMessageBox.critical(self, "Error", "%s" % str(ex))

        return self.setCommandXML('<discard-changes/>', True)

    def _buildCopyXML(self, source, target):
        node = etree.Element("copy-config")
        node.append(datastore_or_url("target", target, self._assert))
        try:
            node.append(datastore_or_url("source", source, self._assert))
        except Exception:
            node.append(validated_element(source, ("source", qualify("source"))))
        return to_xml(node)

    def onActCopyConfig(self):
        dlg = CopyConfiguration(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            log.info("copy accept")
            source = dlg.source()
            target = dlg.target()
            log.info("copy accept, source:%s, target:%s", source, target)
            try:
                xml = self._buildCopyXML(target, source)
            except Exception as ex:
                return QMessageBox.critical(self, "Error", "Target Url or Datastore error.\n%s"%str(ex))
            self.setCommandXML(xml, True)

    def onActDeleteConfig(self):
        dlg = DeleteConfiguration(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            target = dlg.target()
            node = etree.Element("delete-config")
            try:
                node.append(datastore_or_url("target", target, self._assert))
            except Exception as ex:
                return QMessageBox.critical(self, "Error", "target Url or Datastore error.\n%s"%str(ex))
            self.setCommandXML(to_xml(node), True)

    def onActCancelConfirmedCommit(self):
        try:
            for cap in [':candidate', ':confirmed-commit']:
                self._assert(cap)
        except Exception as ex:
            return QMessageBox.critical(self, "Error", "%s" % str(ex))

        dlg = CancelComfirmedCommit(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            persist_id = dlg.persistID
            node = etree.Element("cancel-commit")
            if persist_id is not None:
                etree.SubElement(node, "persist-id").text = persist_id
            self.setCommandXML(to_xml(node), True)

    def _buildCommitXML(self, confirmed=False, timeout=None, persist=None, persist_id=None):
        self._assert(":candidate")
        node = etree.Element("commit")
        if persist and persist_id:
            raise OperationError("Invalid operation as persist cannot be present with persist-id")
        if confirmed :
            self._assert(":confirmed-commit")
            etree.SubElement(node, "confirmed")
            if timeout is not None:
                etree.SubElement(node, "confirm-timeout").text = timeout
            if persist is not None:
                etree.SubElement(node, "persist").text = persist
        if persist_id is not None:
            etree.SubElement(node, "persist-id").text = persist_id
        return to_xml(node)

    def onCommit(self):
        try:
            xml = self._buildCommitXML()
        except Exception as ex:
            return QMessageBox.critical(self, "Error", str(ex))
        return self.setCommandXML(xml, True)

    def onActConfirmedCommit(self):
        dlg = ComfirmedCommit(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                xml = self._buildCommitXML(dlg.confirmed, dlg.confirmTimeout, dlg.persist, dlg.persistId)
            except Exception as ex:
                return QMessageBox.critical(self, "Error", str(ex))
            self.setCommandXML(xml, True)

    def _buildValidateXml(self, source="candidate"):
        self._assert(":validate")

        node = etree.Element("validate")
        if type(source) is str:
            src = datastore_or_url("source", source, self._assert)
        else:
            validated_element(source, ("config", qualify("config")))
            src = etree.Element("source")
            src.append(source)
        node.append(src)
        return to_xml(node)

    def onActValidateConfig(self):
        dlg = ValidateConfiguration(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                xml = self._buildValidateXml(dlg.source)
            except Exception as ex:
                return QMessageBox.critical(self, "Error", str(ex))
            self.setCommandXML(xml, True)

    def onActManageLocks(self):
        dlg = LockUnlockDatastore(self)
        dlg.setLockState(self._datastoreLock)
        dlg.exec()

    def onSessionManager(self):
        dlg = SessionManager(self)
        dlg.exec()

    def onShowCap(self):
        if not self.sessionOperable:
            return

        if not self._capshow and self._proxy.manager:
            self._capshow = CapabilityWidgets(self._proxy.manager.server_capabilities, self)
            self._capshow.setWindowTitle("Capabilities - %s" % self.sessionName)

        self._capshow.raise_()
        self._capshow.activateWindow()
        self._capshow.showNormal()

    def onGetSchema(self):
        if not self.sessionOperable:
            return

        if not self._schemas or not len(self._schemas):
            self._widgetCgroupCtrl(False)
            self._schemas = self._loadSchema()
            self._widgetCgroupCtrl(True)
            if not self._schemas or len(self._schemas) == 0:
                return

        if not self._schemashow:
            self._schemashow = SchemaWidgets(self._schemas)
            self._schemashow.setWindowTitle("Schema - %s" % self.sessionName)
        self._schemashow.show()
        self._schemashow.activateWindow()

    def _getSchemaData(self, schema: dict):
        send_time = QDateTime.currentDateTime()
        rpc, req = self._proxy.get_schema(schema.get('identifier'), schema.get('version'))
        self._sessionHistory.appendHistory(send_time, SessionOperType.Out, req)
        rpc_reply = self._proxy.wait_asnync_reply(rpc)
        cur_time = QDateTime.currentDateTime()
        timediff = send_time.msecsTo(cur_time)
        self._sessionHistory.appendHistory(cur_time, SessionOperType.In, rpc_reply.xml, extra=f'(took {timediff} ms)')
        return rpc_reply.data

    def _loadSchema(self):
        self._appendLog("Start loading schema.")
        process_dlg = QProgressDialog(self, Qt.WindowCloseButtonHint)
        process_dlg.setWindowIcon(QIcon(':/res/yinyang.png'))
        process_dlg.setLabelText("Loading schema list..")
        process_dlg.setMinimumDuration(100)
        process_dlg.setWindowTitle("Schema loading...")
        process_dlg.setModal(True)
        process_dlg.open(self._onBtAbort)
        # process_dlg.open()
        filter=('subtree', '<netconf-state xmlns="urn:ietf:params:xml:ns:yang:ietf-netconf-monitoring"><schemas/></netconf-state>')
        try:
            send_time = QDateTime.currentDateTime()
            rpc, req = self._proxy.get(filter)
            self._sessionHistory.appendHistory(send_time, SessionOperType.Out, req)
            schema_rpy = self._proxy.wait_asnync_reply(rpc)
            cur_time = QDateTime.currentDateTime()
            timediff = '{:,}'.format(send_time.msecsTo(cur_time))
            self._sessionHistory.appendHistory(cur_time, SessionOperType.In, schema_rpy.xml, extra=f'(took {timediff} ms)')
        except Exception as e:
            self._appendLog(f'{str(e)}.', fcolor=Qt.red)
            log.info(str(e))
            process_dlg.close()
            return []
        else:
            netconf_sate = schema_rpy.data
            if netconf_sate == None :
                self._appendLog(f"Get schema list error: {schema_rpy.xml}.")
                process_dlg.close()
                return []
            schema_list = []
            for elm in netconf_sate.iter():
                schemas = elm.findall(qualify('schema', NETCONF_MONITORING_NS))
                for scm in schemas:
                    schemas_dict={}
                    for entity in scm.getchildren():
                        #tag = entity.tag.replace('{%s}' % NETCONF_MONITORING_NS, '')
                        tag = etree.QName(entity).localname
                        val = entity.text
                        schemas_dict[tag] = val
                    schema_list.append(schemas_dict)

            schema_count = len(schema_list)
            self._appendLog(f"Get schema count: {schema_count}.")
            if schema_count == 0:
                process_dlg.close()
                return []

            process_dlg.setRange(0, schema_count)
            for index, schema in enumerate(schema_list):
                process_dlg.setValue(index)
                process_dlg.setLabelText("Load %s@%s.%s" % (schema.get('identifier', '?'),
                                        schema.get('version', '?'), schema.get('format', '?')))
                process_dlg.setWindowTitle("Schema loading... [%d/%d]" % (index, schema_count))
                try:
                    schema['data'] = self._getSchemaData(schema)
                except Exception as e:
                    self._appendLog(f'{str(e)}.', fcolor=Qt.GlobalColor.red)
                    log.info(str(e))
                    process_dlg.close()
                    return []
                if process_dlg.wasCanceled() is True:
                    self._appendLog('User canceled the operation.')
                    process_dlg.close()
                    return [];
            process_dlg.setValue(schema_count)
            self._appendLog("Schema loading done.")
            process_dlg.close()
            return schema_list

    @property
    def connected(self):
        return self._proxy.is_connected

    @property
    def connectInfoStr(self):
        cfg = self._conf_data
        if self.raddr :
            return "[Call Home] %s@%s:%d"%(cfg['user'], self.raddr[0], self.raddr[1])
        return self._connectInfo

    @property
    def sessionName(self):
        name = self._conf_data.get('name', 'unkown')
        if self._conf_data.get('type', 0) == SessionOption.SessionType.NETCONF_CALLHOME:
            return "[Call Home] %s"%name
        return name

    @property
    def displayName(self):
        if len(self._displayName):
            return self._displayName
        else:
            return self.sessionName

    def setDisplayName(self, name):
        self._displayName = name

    @property
    def sesson_id(self):
        if self._proxy.is_connected and self._proxy.manager:
            return self._proxy.manager.session_id
        else:
            return 0

class NotificationModel(QAbstractItemModel):
    def __init__(self, parent: QObject = None ) -> None:
        super().__init__(parent)
        self._notifications = []
        self.horizontalHeader = ['Generated', 'Received', 'Notification', 'origin xml']

    def rowCount(self, parent: QModelIndex = ...) -> int:

        return len(self._notifications)

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
            return self._notifications[index.row()][index.column()]
        if role == Qt.UserRole:
            return self._notifications[index.row()][3]

        return QVariant()

    def setData(self, index: QModelIndex, value: typing.Any, role: int = ...) -> bool:
        if role == Qt.UserRole:
            self._notifications[index.row()][4] = value
            return True
        return False

    def index(self, row: int, column: int, parent: QModelIndex = ...) -> QModelIndex:
        if (row < 0 or row > len(self._notifications)) or (column < 0 or column > len(self.horizontalHeader)):
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
            self._notifications.insert[ar, ["","","",""]]
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
            self._notifications.pop(row)

        self.endRemoveRows()
        return True

    def appendRow(self, eventTime: str, reciveTime: str, notification_name: str, origin: str):
        ntf = [eventTime, reciveTime, notification_name, origin]
        self.beginInsertRows(QModelIndex(), self.rowCount(), self.rowCount())
        self._notifications.append(ntf)
        self.endInsertRows()

    def clear(self):
        self.beginResetModel()
        self._notifications.clear()
        self.endResetModel()

class _NotificationSignals(QObject):
    countChanged = pyqtSignal(int)

class NotificationWidget(QWidget):
    "通告显示控件"
    def __init__(self, parent=None, flags=Qt.Widget) -> None:
        super().__init__(parent, flags)
        self.signal = _NotificationSignals()
        self._initUI()

        timer = QTimer(self)
        timer.setInterval(1000 * 30)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self.setFlowUpMode(True))

        self._flowUpMode = True
        self._flowUpTimer = timer

    def _initUI(self):
        # ntflist = QListView(self)
        ntflist = QTableView(self)
        ntflist.setStyleSheet("QTableView::item{padding-left:10px;padding-right:10px;}")
        ntflist.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        # ntflist.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        ntflist.setAlternatingRowColors(True)
        ntflist.horizontalHeader().setStretchLastSection(True)
        ntflist.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        datamodel = NotificationModel(self)
        proxy_model = QSortFilterProxyModel(self)
        proxy_model.setSourceModel(datamodel)
        proxy_model.setFilterKeyColumn(3)

        ntflist.setModel(proxy_model)
        ntflist.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        ntflist.setSelectionModel(QItemSelectionModel(proxy_model, self))
        ntflist.setSelectionMode(QAbstractItemView.SelectionMode.ContiguousSelection)
        ntflist.selectionModel().currentChanged.connect(self._onCurrentChanged)
        ntflist.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        ntflist.customContextMenuRequested.connect(self._onCustomMenuRequest)

        # ntflist.setColumnHidden(3, True)
        ntflist.hideColumn(3)

        # ntflist.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        ntflist.horizontalHeader().setDefaultSectionSize(160)
        ntflist.horizontalHeader().resizeSection(0, 150)
        # ntflist.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        ntflist.verticalHeader().setDefaultSectionSize(8)
        ntflist.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)

        preview = XmlEdit(self, "Notification")
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
        llayout.addWidget(ntflist)

        right_frame = QFrame(self)
        rlayout = QVBoxLayout(right_frame)
        rlayout.setContentsMargins(0, 0, 0, 0)
        rlayout.addWidget(preview)

        splitter = QSplitter(self)
        splitter.setHandleWidth(2)
        splitter.addWidget(left_frame)
        splitter.addWidget(right_frame)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 5)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        act_copy = QAction("&Copy to Clipboard", self)
        act_copy.triggered.connect(self._onCopy)
        act_copy.setShortcut(QKeySequence.Copy)
        act_copy.setShortcutContext(Qt.WidgetShortcut)

        ntflist.addAction(act_copy)

        self._preview = preview
        self._bt_filter = bt_filter
        self._filter_edit = filter_edit
        self._proxy_model = proxy_model
        self.datamodel = datamodel
        self.ntflist = ntflist
        self._actCopy = act_copy

    def _onCustomMenuRequest(self, pos: QPoint):
        menu = QMenu(self)
        act_delete = QAction("Remove", menu)
        act_delete.triggered.connect(self._onDeleteItem)

        act_deleteAll = QAction("Remove All", menu)
        act_deleteAll.triggered.connect(self._onDeleteAll)

        act_export = QAction("Export to File...")
        act_export.triggered.connect(self._onExport)

        index = self.ntflist.indexAt(pos)
        if index.isValid():
            menu.addAction(act_delete)
        menu.addAction(act_deleteAll)

        menu.addSeparator()
        if index.isValid():
            menu.addAction(self._actCopy)

        if not len(self.ntflist.selectedIndexes()):
            act_export.setEnabled(False)

        if self._proxy_model.rowCount() < 1:
            act_deleteAll.setEnabled(False)

        menu.addAction(act_export)
        menu.exec(QCursor.pos())

    def _onDeleteItem(self):
        sel_indexs = self.ntflist.selectedIndexes()
        self._proxy_model.removeRows(sel_indexs[0].row(), int(len(sel_indexs)/3))
        self.signal.countChanged.emit(self.datamodel.rowCount())

    def _onDeleteAll(self):
        self.datamodel.clear()
        self._preview.clear()
        self.signal.countChanged.emit(self.datamodel.rowCount())

    def _selectItemToText(self):
        sel_indexs = self.ntflist.selectedIndexes()
        rows = []
        for oidx in sel_indexs:
            idx = self._proxy_model.mapToSource(oidx)
            if idx.row() not in rows:
                rows.append(idx.row())
        text = ""
        for row in rows:
            gen_idx = self.datamodel.index(row, 0)
            time_idx = self.datamodel.index(row, 1)
            name_idx = self.datamodel.index(row, 2)

            title = "<!-- Recevied=%s, Name=%s, Genertated=%s -->\n"%(
                self.datamodel.data(time_idx, Qt.DisplayRole),
                self.datamodel.data(name_idx, Qt.DisplayRole),
                self.datamodel.data(gen_idx, Qt.DisplayRole))
            text += title
            text += pretty_xml(self.datamodel.data(gen_idx, Qt.UserRole))
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

    # def _onListClicked(self):
    #     cindex = self.ntflist.currentIndex()
    #     log.debug("cindex: %d, proxy row count:%d", cindex.row(),  self._proxy_model.rowCount()-1)
    #     if cindex.row() != self._proxy_model.rowCount()-1:
    #         self.setFlowUpMode(False)
    #         self._flowUpTimer.start()
    #     else:
    #         self.setFlowUpMode(True)

    def appendNotification(self, receiveTime: QDateTime, ntf: NotificationM):
        eventTime =QDateTime.fromString(ntf.event_time, Qt.ISODate)
        event_time = eventTime.toString("yyyy-MM-dd hh:mm:ss")

        # ntf = to_ele(xml)
        # for elm in etree.ElementChildIterator(ntf):
        #     localname = etree.QName(elm).localname
        #     if localname == 'eventTime':
        #         eventTime =QDateTime.fromString(elm.text, Qt.ISODate)
        #         event_time = eventTime.toString("yyyy-MM-dd hh:mm:ss")
        #     else:
        #         ntfname = localname
        # if not ntfname :
        #     return log.error("No nitification name find")
        recevied_time = receiveTime.toString("yyyy-MM-dd hh:mm:ss.zzz")
        self.datamodel.appendRow(event_time, recevied_time, ntf.notifcaiton_name, ntf.notification_xml)

        rowcount = self._proxy_model.rowCount();
        if self._flowUpMode or rowcount == 1:
            row = rowcount - 1
            urow = 0 if row < 0 else row
            colum = self.ntflist.currentIndex().column()
            ucolum = 0 if colum < 0 else colum
            log.debug("setCurrentIndex: %d, %d", urow, ucolum)
            self.ntflist.setCurrentIndex(self._proxy_model.index(urow, ucolum))

        # 第一次收到数据，做一次宽度调整
        if rowcount <= 1:
            self.ntflist.resizeColumnToContents(0)
            self.ntflist.resizeColumnToContents(1)

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
        oindex = self.ntflist.currentIndex()
        index = self._proxy_model.mapToSource(oindex)
        if index.isValid():
            self._preview.setXml(self.datamodel.data(index, Qt.UserRole))

        return super().showEvent(a0)

class SchemaWidgets(QWidget):
    def __init__(self, schemas={}, parent=None, flags=Qt.Window) -> None:
        super().__init__(parent, flags)
        self._initUI()
        self._updateView(schemas)

    def _initUI(self):
        if sys.platform == 'cygwin' or sys.platform == 'win32':
            self.setWindowIcon(QIcon(':/res/yinyang.png'))
        self.findw = None
        layout = QVBoxLayout(self)

        list_frame = QFrame(self)
        list_frame.setContentsMargins(0, 0, 0, 0)
        hlayout = QHBoxLayout()
        self._bt_filter = QCheckBox('Filter', self)
        self._bt_filter.setChecked(True)
        self._filter_edit = QLineEdit(self)
        self._filter_edit.setPlaceholderText("Regular expression")
        hlayout.addWidget(self._bt_filter)
        hlayout.addWidget(self._filter_edit, 1)

        view = QListView(self)
        view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        view.setAlternatingRowColors(True)
        view.pressed.connect(self._onPressViewList)
        data_model = QStandardItemModel(self)
        proxy_model = QSortFilterProxyModel(self)
        proxy_model.setSourceModel(data_model)
        view.setModel(proxy_model)

        left_layout = QVBoxLayout(list_frame)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Schema List:", self))
        left_layout.addLayout(hlayout)
        left_layout.addWidget(view)

        content_frame = QFrame(self)
        content_frame.setContentsMargins(0, 0, 0, 0)

        content = QPlainTextEdit(self)
        content.setReadOnly(True)
        content.setObjectName("Schema")
        content.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        content.customContextMenuRequested.connect(self._onResponseMenuRequestd)

        find_act = QAction("Find", content)
        find_act.setShortcut(QKeySequence.Find)
        find_act.triggered.connect(self.onFindAction)
        find_act.setShortcutContext(Qt.WidgetShortcut)
        content.addAction(find_act)

        right_layout = QVBoxLayout(content_frame)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("Content", self))
        right_layout.addWidget(content)

        bottom_layout = QHBoxLayout()
        count = QLabel("", self)
        bottom_layout.addWidget(count)
        bottom_layout.addStretch(1)
        # bt_refresh = QPushButton("Refresh", self)
        bt_ok = QPushButton("OK", self)
        bt_ok.clicked.connect(self.close)
        bt_ok.setDefault(True)
        # bottom_layout.addWidget(bt_refresh)
        bottom_layout.addWidget(bt_ok)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(list_frame)
        splitter.addWidget(content_frame)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)

        action_save = QAction("&Save as", self)
        action_save.setShortcut(QKeySequence.SaveAs)
        action_save.setShortcutContext(Qt.WidgetShortcut)
        action_save.triggered.connect(self._onActionSaveAs)
        view.addAction(action_save)
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)

        layout.addWidget(splitter)
        layout.addLayout(bottom_layout)

        self._content = content
        # self._bt_refresh = bt_refresh
        self._schema_view = view
        self._proxy_model = proxy_model
        self._data_model = data_model
        self._schema_count = count

        self._bt_filter.stateChanged.connect(self._onBtFilterStateChanged)
        self._filter_edit.textChanged.connect(self._onFilterChanged)

        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.resize(600, 450)

    def _onResponseMenuRequestd(self, pos: QPoint):
        menu = self._content.createStandardContextMenu()

        act_find = QAction("&Find", menu)
        act_find.setShortcut(QKeySequence.Find)
        act_find.triggered.connect(self.onFindAction)

        if not len(self._content.toPlainText()):
            act_find.setEnabled(False)

        menu.addSeparator()
        menu.addAction(act_find)
        menu.exec(QCursor.pos())
        del menu

    def onFindAction(self):
        log.debug("onFindAction trigred.")
        if not self.findw :
            self.findw = FindDialg(self._content)
            if len(self._content.objectName()):
                self.findw.setWindowTitle("Find in %s"%self._content.objectName())
        self.findw.popUpShow()

    def _onActionSaveAs(self):
        indexs = self._schema_view.selectedIndexes()
        if len(indexs) == 0:
            return
        file_dlg = QFileDialog(self)
        file_dlg.setWindowTitle("Select Folder")
        file_dlg.setAcceptMode(QFileDialog.AcceptOpen)
        file_dlg.setViewMode(QFileDialog.Detail)
        # file_dlg.setOption(QFileDialog.ShowDirsOnly)
        file_dlg.setFileMode(QFileDialog.DirectoryOnly)
        if file_dlg.exec() != QDialog.Accepted:
            return
        dir = file_dlg.selectedFiles()
        path = dir[0]
        for index in indexs:
            dindex = self._proxy_model.mapToSource(index)
            yangtext = self._data_model.data(dindex, Qt.UserRole)
            if yangtext is not None:
                fname = self._data_model.data(dindex, Qt.DisplayRole)
                wf = os.path.join(path, fname)
                with open(wf, 'w+') as f:
                    f.write(yangtext)

    def _updateView(self, schemas):
        # log.info("get schemas: %s", schema_list)
        for schema in schemas:
            vitem = QStandardItem('%s@%s.%s' % (schema.get('identifier', '?'), schema.get('version','?'), schema.get('format', '?')))
            vitem.setData(schema.get('data', None), Qt.UserRole)
            vitem.setData(schema, Qt.UserRole + 1)
            self._data_model.appendRow(vitem)
        self._proxy_model.sort(0, Qt.AscendingOrder)
        self._schema_count.setText(self.tr('Total: ') + str(len(schemas)))

    def appendSchema(self, schema: dict):
        if isinstance(schema, dict):
            vitem = QStandardItem('%s@%s.%s' % (schema.get('identifier', '?'), schema.get('version','?'), schema.get('format', '?')))
            vitem.setData(schema.get('data', None), Qt.UserRole)
            vitem.setData(schema, Qt.UserRole + 1)
            self._data_model.appendRow(vitem)

    def _onBtFilterStateChanged(self, sta: int):
        ftext = ""
        if sta == 2:
            ftext = self._filter_edit.text()
        regExp = QRegExp(ftext, Qt.CaseInsensitive,
                         QRegExp.PatternSyntax.WildcardUnix)
        self._proxy_model.setFilterRegExp(regExp)

    def _onFilterChanged(self, s):
        if self._bt_filter.isChecked():
            regExp = QRegExp(s, Qt.CaseInsensitive,
                             QRegExp.PatternSyntax.WildcardUnix)
            self._proxy_model.setFilterRegExp(regExp)

    def _onPressViewList(self, index: QModelIndex):
        dindex = self._proxy_model.mapToSource(index)
        self._content.setPlainText(self._data_model.data(dindex, Qt.UserRole))


class CapabilityWidgets(QWidget):
    def __init__(self, caps=[], parent = None, flags = Qt.Window) -> None:
        super().__init__(parent, flags)
        if sys.platform == 'cygwin' or sys.platform == 'win32':
            self.setWindowIcon(QIcon(QIcon(':/res/capability.png')))
        vlayout = QVBoxLayout(self)
        view = QListView(self)
        view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        view.setAlternatingRowColors(True)

        model = QStringListModel(self)
        model.setStringList(caps)

        self._proxy_model = QSortFilterProxyModel(self)
        self._proxy_model.setSourceModel(model)
        self._proxy_model.setFilterKeyColumn(0)
        view.setModel(self._proxy_model)
        self._proxy_model.sort(0, Qt.AscendingOrder)

        action_copy = QAction("&Copy to Clipboard", self)
        action_copy.setShortcut(QKeySequence.Copy)
        action_copy.setShortcutContext(Qt.WidgetShortcut)
        action_copy.triggered.connect(self._actionCopy)
        view.addAction(action_copy)
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)

        hlayout = QHBoxLayout()
        self._bt_filter = QCheckBox('Filter', self)
        self._bt_filter.setChecked(True)
        self._filter_edit = QLineEdit(self)
        self._filter_edit.setPlaceholderText("Regular expression")

        hlayout.addSpacing(5)
        hlayout.addWidget(self._bt_filter)
        hlayout.addWidget(self._filter_edit, 1)

        vlayout.addLayout(hlayout)
        vlayout.addWidget(view, 1)

        self._bt_filter.stateChanged.connect(self._onBtFilterStateChanged)
        self._filter_edit.textChanged.connect(self._onFilterChanged)
        self._view = view
        self._data_model = model

        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.resize(450, 600)

    def _onBtFilterStateChanged(self, sta: int):
        ftext =""
        if sta == 2:
            ftext = self._filter_edit.text()
        regExp = QRegExp(ftext, Qt.CaseInsensitive,
                         QRegExp.PatternSyntax.WildcardUnix)
        self._proxy_model.setFilterRegExp(regExp)

    def _onFilterChanged(self, s):
        if self._bt_filter.isChecked():
            regExp = QRegExp(s, Qt.CaseInsensitive,
                             QRegExp.PatternSyntax.WildcardUnix)
            self._proxy_model.setFilterRegExp(regExp)

    def _actionCopy(self):
        indexs = self._view.selectedIndexes()
        if len(indexs) == 0:
            return
        text = ""
        for index in indexs:
            dindex = self._proxy_model.mapToSource(index)
            text += self._data_model.data(dindex,
                                          Qt.ItemDataRole.DisplayRole) + "\n"
        QApplication.clipboard().setText(text)

    def updateCapability(self, caps:[]):
        self._proxy_model.sourceModel().setStringList(caps)

    # def closeEvent(self, a0: QCloseEvent) -> None:
    #     self.hide()
    #     a0.ignore()

class CopyConfiguration(QDialog):
    def __init__(self, parent=None, flags=Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint) -> None:
        super().__init__(parent, flags)
        self.setWindowTitle("Copy Configuration")
        self.setWindowIcon(QIcon(':/res/copy.png'))
        # Source groupbox

        rb_srcUrl = QRadioButton("URL", self)
        ed_srcUrl = QLineEdit(self)
        ed_srcUrl.setToolTip('http://, file://, ftp:// ...')
        ed_srcUrl.setEnabled(False)

        rb_srcDatastore = QRadioButton("Datastore", self)
        rb_srcDatastore.setChecked(True)
        com_srcDataStore = QComboBox(self)
        com_srcDataStore.addItems(['running', 'candidate', 'startup'])

        src_bt_group = QButtonGroup(self)
        src_bt_group.addButton(rb_srcUrl, 0)
        src_bt_group.addButton(rb_srcDatastore, 1)
        src_bt_group.buttonClicked.connect(self._onSourceSelectChange)

        source_group = QGroupBox('Source', self)
        source_layout = QGridLayout(source_group)
        source_layout.addWidget(rb_srcUrl, 0, 0)
        source_layout.addWidget(ed_srcUrl, 0, 1)
        source_layout.addWidget(rb_srcDatastore, 1, 0)
        source_layout.addWidget(com_srcDataStore, 1, 1)

        # Target groupbox
        rb_targetUrl = QRadioButton("URL", self)
        ed_targeUrl = QLineEdit(self)
        ed_targeUrl.setToolTip('http://, file://, ftp:// ...')
        ed_targeUrl.setEnabled(False)

        rb_targetDatastore = QRadioButton("Datastore", self)
        rb_targetDatastore.setChecked(True)
        com_targetDataStore = QComboBox(self)
        com_targetDataStore.addItems(['candidate', 'running', 'startup'])

        target_bt_group = QButtonGroup(self)
        target_bt_group.addButton(rb_targetUrl, 0)
        target_bt_group.addButton(rb_targetDatastore, 1)
        target_bt_group.buttonClicked.connect(self._onTargetSelectChange)

        target_group = QGroupBox('Target', self)
        target_layout = QGridLayout(target_group)
        target_layout.addWidget(rb_targetUrl, 0, 0)
        target_layout.addWidget(ed_targeUrl, 0, 1)
        target_layout.addWidget(rb_targetDatastore, 1, 0)
        target_layout.addWidget(com_targetDataStore, 1, 1)

        # bottom
        bt_copy = QPushButton("Copy", self)
        bt_copy.clicked.connect(self._onAccept)
        bt_cancel = QPushButton("Cancel", self)
        bt_cancel.setDefault(True)
        bt_cancel.clicked.connect(self.close)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch(1)
        bottom_layout.addSpacing(180)
        bottom_layout.addWidget(bt_copy)
        bottom_layout.addWidget(bt_cancel)

        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SetFixedSize)
        layout.addWidget(source_group)
        layout.addWidget(target_group)
        layout.addLayout(bottom_layout)

        self.sourceType = src_bt_group
        self.srcUrl = ed_srcUrl
        self.srcDataStore = com_srcDataStore

        self.targetType = target_bt_group
        self.targetUrl = ed_targeUrl
        self.targetDataStore = com_targetDataStore

    def _onAccept(self):
        if ((self.sourceType.checkedId() == 0 and '://' not in self.srcUrl.text())
            or((self.targetType.checkedId() == 0 and '://' not in self.targetUrl.text()) )):
            return QMessageBox.critical(self, "Error", "Invald URL format.")
        self.accept()

    def _onTargetSelectChange(self):
        if self.targetType.checkedId() == 0:
            self.targetUrl.setEnabled(True)
            self.targetDataStore.setEnabled(False)
        else:
            self.targetUrl.setEnabled(False)
            self.targetDataStore.setEnabled(True)

    def _onSourceSelectChange(self):
        if self.sourceType.checkedId() == 0:
            self.srcUrl.setEnabled(True)
            self.srcDataStore.setEnabled(False)
        else:
            self.srcUrl.setEnabled(False)
            self.srcDataStore.setEnabled(True)

    def source(self):
        if self.sourceType.checkedId() == 0:
            return self.srcUrl.text()
        else:
            return self.srcDataStore.currentText()

    def target(self):
        if self.targetType.checkedId() == 0:
            return self.targetUrl.text()
        else:
            return self.targetDataStore.currentText()

class DeleteConfiguration(QDialog):
    def __init__(self, parent=None, flags=Qt.Dialog | Qt.WindowCloseButtonHint) -> None:
        super().__init__(parent, flags)
        self.setWindowTitle("Delete Configuration")
        self.setWindowIcon(QIcon(':/res/no-register.png'))
         # Target groupbox
        rb_targetUrl = QRadioButton("URL", self)
        ed_targeUrl = QLineEdit(self)
        ed_targeUrl.setToolTip('http://, file://, ftp:// ...')
        ed_targeUrl.setEnabled(False)

        rb_targetDatastore = QRadioButton("startup", self)
        rb_targetDatastore.setChecked(True)

        target_bt_group = QButtonGroup(self)
        target_bt_group.addButton(rb_targetUrl, 0)
        target_bt_group.addButton(rb_targetDatastore, 1)
        target_bt_group.buttonClicked.connect(self._onSelectChange)

        target_group = QGroupBox('Target', self)
        target_layout = QGridLayout(target_group)
        target_layout.addWidget(rb_targetUrl, 0, 0)
        target_layout.addWidget(ed_targeUrl, 0, 1)
        target_layout.addWidget(rb_targetDatastore, 1, 0)

        # bottom
        bt_copy = QPushButton("Delete", self)
        bt_copy.clicked.connect(self._onAccept)
        bt_cancel = QPushButton("Cancel", self)
        bt_cancel.setDefault(True)
        bt_cancel.clicked.connect(self.close)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch(1)
        bottom_layout.addSpacing(150)
        bottom_layout.addWidget(bt_copy)
        bottom_layout.addWidget(bt_cancel)

        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SetFixedSize)
        layout.addWidget(target_group)
        layout.addLayout(bottom_layout)

        self.targetType = target_bt_group
        self.targetUrl = ed_targeUrl

    def _onAccept(self):
        if (self.targetType.checkedId() == 0 and '://' not in self.targetUrl.text()):
            return QMessageBox.critical(self, "Error", "Invald URL format.")
        self.accept()

    def _onSelectChange(self):
        if self.targetType.checkedId() == 0:
            self.targetUrl.setEnabled(True)
        else:
            self.targetUrl.setEnabled(False)

    def target(self):
        if self.targetType.checkedId() == 0:
            return self.targetUrl.text()
        else:
            return 'startup'

class ComfirmedCommit(QDialog):
    def __init__(self, parent=None, flags=Qt.Dialog | Qt.WindowCloseButtonHint) -> None:
        super().__init__(parent, flags)
        self.setWindowTitle("Confirmed Commit")
        self.setWindowIcon(QIcon(':/res/confirm-commit.png'))
        rb_confirmed = QRadioButton("Confirmed Commit", self)
        rb_confirmed.setChecked(True)

        rb_followup = QRadioButton("Follow-up confirmed commit", self)
        rb_confirming = QRadioButton("Confirming commit")

        bt_group = QButtonGroup(self)
        bt_group.addButton(rb_confirmed, 0)
        bt_group.addButton(rb_followup, 1)
        bt_group.addButton(rb_confirming, 2)
        bt_group.buttonClicked.connect(self._onSelectTypeChanged)

        operation_group = QGroupBox("Type of operation", self)
        oper_layout = QVBoxLayout(operation_group)
        oper_layout.addWidget(rb_confirmed)
        oper_layout.addWidget(rb_followup)
        oper_layout.addWidget(rb_confirming)

        ed_confirm_timeout = QLineEdit(self)
        ed_confirm_timeout.setText("600")
        ed_confirm_timeout.setEnabled(False)

        ed_persist = QLineEdit(self)
        ed_persist.setEnabled(False)

        cb_confirm_timeout = QCheckBox(self)
        cb_confirm_timeout.stateChanged.connect(lambda sta: self._ed_confirm_timeout.setEnabled(True if sta == 2 else False))
        cb_persist = QCheckBox(self)
        cb_persist.stateChanged.connect(lambda sta: self._ed_persist.setEnabled(True if sta == 2 else False))
        label = QLabel("Persist", self)
        param_group = QGroupBox("Parameters", self)
        param_layout = QGridLayout(param_group)
        param_layout.addWidget(QLabel("Confirm timeout", self), 0, 0)
        param_layout.addWidget(ed_confirm_timeout, 0, 1)
        param_layout.addWidget(cb_confirm_timeout, 0, 2)
        param_layout.addWidget(label, 1, 0)
        param_layout.addWidget(ed_persist, 1, 1)
        param_layout.addWidget(cb_persist, 1, 2)

        # bottom
        bt_Ok= QPushButton("OK", self)
        bt_Ok.clicked.connect(self.accept)
        bt_cancel = QPushButton("Cancel", self)
        bt_cancel.setDefault(True)
        bt_cancel.clicked.connect(self.close)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch(1)
        bottom_layout.addSpacing(150)
        bottom_layout.addWidget(bt_Ok)
        bottom_layout.addWidget(bt_cancel)

        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SetFixedSize)
        layout.addWidget(operation_group)
        layout.addWidget(param_group)
        layout.addLayout(bottom_layout)

        self._ed_confirm_timeout = ed_confirm_timeout
        self._ed_persist = ed_persist
        self._cb_confirm_timeout = cb_confirm_timeout
        self._cb_persist = cb_persist
        self._operationType = bt_group
        self._presistLable = label

    def _onSelectTypeChanged(self):
        cid = self._operationType.checkedId()
        if cid == 0:
            self._cb_confirm_timeout.setChecked(False)
            self._cb_confirm_timeout.setEnabled(True)
            self._presistLable.setText("Persist")
        elif cid == 1:
            self._cb_confirm_timeout.setChecked(False)
            self._cb_confirm_timeout.setEnabled(True)
            self._presistLable.setText("Persist ID")
        else:
            self._cb_confirm_timeout.setChecked(False)
            self._cb_confirm_timeout.setEnabled(False)
            self._presistLable.setText("Persist ID")

    @property
    def confirmed(self):
        if self._operationType.checkedId() == 2:
            return False
        else:
            return True

    @property
    def confirmTimeout(self):
        if self._cb_confirm_timeout.isChecked() and self._operationType.checkedId() != 2:
            return self._ed_confirm_timeout.text()
        return None

    @property
    def persist(self):
        if self._cb_persist.isChecked() and self._operationType.checkedId() == 0:
            return self._ed_persist.text()
        return None

    @property
    def persistId(self):
        if self._cb_persist.isChecked() and self._operationType.checkedId() != 0:
            return self._ed_persist.text()
        return None

class CancelComfirmedCommit(QDialog):
    def __init__(self, parent=None, flags=Qt.Dialog | Qt.WindowCloseButtonHint) -> None:
        super().__init__(parent, flags)
        self.setWindowTitle("Cancel Commit")
        self.setWindowIcon(QIcon(':/res/cancel-commit.png'))
        ed_persist = QLineEdit(self)
        ed_persist.setEnabled(False)

        cb_persist = QCheckBox(self)
        cb_persist.stateChanged.connect(lambda sta: self._ed_persist.setEnabled(True if sta == 2 else False))

        # bottom
        bt_Ok= QPushButton("OK", self)
        bt_Ok.clicked.connect(self.accept)
        bt_cancel = QPushButton("Cancel", self)
        bt_cancel.setDefault(True)
        bt_cancel.clicked.connect(self.close)

        persist_layout = QHBoxLayout()
        persist_layout.addWidget(QLabel("Persist ID", self))
        persist_layout.addWidget(ed_persist, 1)
        persist_layout.addWidget(cb_persist)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch(1)
        bottom_layout.addSpacing(100)
        bottom_layout.addWidget(bt_Ok)
        bottom_layout.addWidget(bt_cancel)

        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SetFixedSize)
        layout.addLayout(persist_layout)
        layout.addLayout(bottom_layout)

        self._ed_persist = ed_persist
        self._cb_persist = cb_persist

    @property
    def persistID(self):
        if self._cb_persist.isChecked():
            return self._ed_persist.text()
        return None

class ValidateConfiguration(QDialog):
    def __init__(self, parent=None, flags=Qt.Dialog | Qt.WindowCloseButtonHint) -> None:
        super().__init__(parent, flags)
        self.setWindowTitle("Validate")
        # Source groupbox
        rb_srcUrl = QRadioButton("URL", self)
        ed_srcUrl = QLineEdit(self)
        ed_srcUrl.setToolTip('http://, file://, ftp:// ...')
        ed_srcUrl.setEnabled(False)

        rb_srcDatastore = QRadioButton("Datastore", self)
        rb_srcDatastore.setChecked(True)
        com_srcDataStore = QComboBox(self)
        com_srcDataStore.addItems(['running', 'candidate', 'startup'])

        src_bt_group = QButtonGroup(self)
        src_bt_group.addButton(rb_srcUrl, 0)
        src_bt_group.addButton(rb_srcDatastore, 1)
        src_bt_group.buttonClicked.connect(self._onSourceSelectChange)

        source_group = QGroupBox('Source', self)
        source_layout = QGridLayout(source_group)
        source_layout.addWidget(rb_srcUrl, 0, 0)
        source_layout.addWidget(ed_srcUrl, 0, 1)
        source_layout.addWidget(rb_srcDatastore, 1, 0)
        source_layout.addWidget(com_srcDataStore, 1, 1)

        # bottom
        bt_Ok = QPushButton("Validate", self)
        bt_Ok.clicked.connect(self._onAccept)
        bt_cancel = QPushButton("Cancel", self)
        bt_cancel.setDefault(True)
        bt_cancel.clicked.connect(self.close)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch(1)
        bottom_layout.addSpacing(180)
        bottom_layout.addWidget(bt_Ok)
        bottom_layout.addWidget(bt_cancel)

        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SetFixedSize)
        layout.addWidget(source_group)
        layout.addLayout(bottom_layout)

        self.sourceType = src_bt_group
        self.srcUrl = ed_srcUrl
        self.srcDataStore = com_srcDataStore

    def _onSourceSelectChange(self):
        if self.sourceType.checkedId() == 0:
            self.srcUrl.setEnabled(True)
            self.srcDataStore.setEnabled(False)
        else:
            self.srcUrl.setEnabled(False)
            self.srcDataStore.setEnabled(True)

    def _onAccept(self):
        if self.sourceType.checkedId() == 0 and '://' not in self.srcUrl.text():
            return QMessageBox.critical(self, "Error", "Invald URL format.")
        self.accept()

    @property
    def source(self):
        if self.sourceType.checkedId() == 0:
            return self.srcUrl.text()
        else:
            return self.srcDataStore.currentText()

class LockUnlockDatastore(QDialog):
    def __init__(self, parent=None, flags=Qt.Dialog | Qt.WindowCloseButtonHint) -> None:
        super().__init__(parent, flags)
        self.setWindowTitle("Manager Configuration Locks")
        self.setWindowIcon(QIcon(':/res/lock.png'))
        self.session = parent
        targets = ['candidate', 'running', 'startup']

        groupbox = QGroupBox("Target Lock/Unlock", self)
        grouplayout = QVBoxLayout(groupbox)
        cb_group = QButtonGroup(self)
        cb_group.setExclusive(False)
        cb_group.buttonClicked.connect(self.onButtonClicked)
        for id, target in enumerate(targets):
            cb = QCheckBox(target, self)
            cb_group.addButton(cb, id)
            grouplayout.addWidget(cb)
        # bottom
        bt_Ok = QPushButton("OK", self)
        bt_Ok.clicked.connect(self.close)
        bt_Ok.setDefault(True)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch(1)
        bottom_layout.addSpacing(200)
        bottom_layout.addWidget(bt_Ok)

        layout = QVBoxLayout(self)
        # layout.setSizeConstraint(QLayout.SetFixedSize)
        layout.addWidget(groupbox)
        layout.addStretch(1)
        layout.addLayout(bottom_layout)
        self.cb_group = cb_group

    def setLockState(self, lockState: dict):
        for bt in self.cb_group.buttons():
            bt.setChecked(lockState.get(bt.text(), False))

    def _buildLockUnlockXml(self, type='lock', target='candidate'):
        if type not in ['lock', 'unlock']:
            raise TypeError("Type: %s is unsupported."%type)
        if target not in ['candidate', 'running', 'startup', 'sdn']:
            raise ValueError("Target: %s is unsupported."%target)

        node = etree.Element(type)
        etree.SubElement(etree.SubElement(node, "target"), target)
        return to_xml(node)

    def onButtonClicked(self, button: QAbstractButton):
        checked = button.isChecked()
        # log.debug('button %s toggled, state: %s', button.text(), checked)
        xml = self._buildLockUnlockXml('lock' if checked else 'unlock', button.text())
        if self.session:
            rsp = self.session.setCommandXML(xml, True)
            if not rsp or not rsp.ok and checked:
                button.setChecked(False if checked else True) # 恢复勾选状态

class SessionInfoModel(QAbstractItemModel):
    def __init__(self, parent: QObject = None ) -> None:
        super().__init__(parent)
        self.currentSessionId = -1
        self._sessions = []
        self.horizontalHeader = ['session-id', 'transport', 'username', 'source-host', 'login-time',
                                 'in-rpcs', 'in-bad-rpcs', 'out-rpc-errors', 'out-notifications']

    def rowCount(self, parent: QModelIndex = ...) -> int:

        return len(self._sessions)

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
            if (int(self._sessions[index.row()][0]) == self.currentSessionId
                and index.column() == 0):
                return "<<%s>>"%self._sessions[index.row()][index.column()]
            return self._sessions[index.row()][index.column()]
        if role == Qt.TextAlignmentRole:
            return Qt.AlignCenter
        # if role == Qt.BackgroundColorRole:
        #     log.info("index sessionID %d, currentSessionId %d",
        #              int(self._sessions[index.row()][0]),
        #              self.currentSessionId)
        #     if int(self._sessions[index.row()][0]) == self.currentSessionId:
        #         return QColor("#FFE6BF")
        return QVariant()

    # def setData(self, index: QModelIndex, value: typing.Any, role: int = ...) -> bool:
    #     if role == Qt.UserRole:
    #         self._sessions[index.row()][4] = value
    #         return True
    #     return False

    def index(self, row: int, column: int, parent: QModelIndex = ...) -> QModelIndex:
        if (row < 0 or row > len(self._sessions)) or (column < 0 or column > len(self.horizontalHeader)):
            return QModelIndex()

        return self.createIndex(row, column)
        # return super().index(row, column, parent)

    def removeRows(self, row: int, count: int, parent: QModelIndex = ...) -> bool:
        if count == 0:
            return False
        if parent.isValid():
            self.beginRemoveRows(parent, row, row + count - 1)
        else:
            self.beginRemoveRows(QModelIndex(), row, row + count - 1)

        # log.debug("removeRows: row %d, count:%d", row, count)
        for ar in range(row, row + count, 1):
            self._sessions.pop(row)

        self.endRemoveRows()
        return True

    def appendRow(self, sessionInfo: list):
        self.beginInsertRows(QModelIndex(), self.rowCount(), self.rowCount())
        if sessionInfo :
            for info in sessionInfo:
                new_session = []
                for head in self.horizontalHeader:
                    new_session.append(info.get(head, ""))
                self._sessions.append(new_session)
        self.endInsertRows()

    def clear(self, new=None):
        self.beginResetModel()
        self._sessions.clear()
        if new :
            for info in new:
                new_session = []
                for head in self.horizontalHeader:
                    new_session.append(info.get(head, ""))
                self._sessions.append(new_session)
        self.endResetModel()

    def sessionId(self, index: QModelIndex):
        if ((index.row() > self.rowCount() or index.row() < 0)
            or (index.column() > self.columnCount() or index.column() < 0)):
            return -1
        return int(self._sessions[index.row()][0])

    def setCurrentSessionId(self, id: int):
        self.currentSessionId = id

class SessionManager(QDialog):
    """会话管理"""
    def __init__(self, parent=None, flags=Qt.Dialog | Qt.WindowCloseButtonHint) -> None:
        super().__init__(parent, flags)
        self.setWindowTitle("Session Manager")
        self.setWindowIcon(QIcon(':/res/session-manager.png'))
        self.session = parent
        self._initUI()

    def _initUI(self):
        view = QTableView(self)
        view.setStyleSheet("QTableView::item{padding-left:10px;padding-right:10px;}")

        view.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        # view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        view.setAlternatingRowColors(True)
        view.horizontalHeader().setStretchLastSection(True)
        view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

        datamodel = SessionInfoModel(self)
        proxy_model = QSortFilterProxyModel(self)
        proxy_model.setSourceModel(datamodel)
        # proxy_model.setFilterKeyColumn(3)

        view.setModel(proxy_model)
        view.horizontalHeader().setHighlightSections(True)
        # view.horizontalHeader().resizeSection(4, 160)
        view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        view.setSelectionModel(QItemSelectionModel(proxy_model, self))
        view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        view.customContextMenuRequested.connect(self._onCustomMenuRequest)

        bt_ok = QPushButton("OK", self)
        bt_ok.clicked.connect(self.close)
        bt_ok.setDefault(True)

        bt_kill = QPushButton("Kill Session", self)
        bt_kill.clicked.connect(self._onKillSession)

        bt_refresh = QPushButton("Refresh", self)
        bt_refresh.clicked.connect(self._onRefreshInfo)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch(1)
        bottom_layout.addSpacing(400)
        bottom_layout.addWidget(bt_kill)
        bottom_layout.addWidget(bt_refresh)
        bottom_layout.addWidget(bt_ok)

        layout = QVBoxLayout(self)
        layout.addWidget(view, 1)
        layout.addLayout(bottom_layout)

        session_list = self.getSessionInfo()
        datamodel.clear(session_list)
        view.resizeColumnsToContents()

        if self.session:
            datamodel.setCurrentSessionId(int(self.session.sesson_id))
        self.view = view
        self.datamodel = datamodel

    def _onCustomMenuRequest(self, pos: QPoint):
        menu = QMenu(self)
        act_kill = QAction("Kill Session", menu)
        act_kill.triggered.connect(self._onKillSession)
        act_refresh = QAction("Refresh", menu)
        act_refresh.triggered.connect(self._onRefreshInfo)

        menu.addAction(act_refresh)
        index = self.view.indexAt(pos)
        if index.isValid():
            menu.addAction(act_kill)

        menu.exec(QCursor.pos())

    def _onRefreshInfo(self):
        sessions = self.getSessionInfo()
        self.datamodel.clear(sessions)

    def _onKillSession(self):
        cindex = self.view.currentIndex()
        session_id = self.datamodel.sessionId(cindex)
        if session_id < 0:
            return
        ans = QMessageBox.question(self, "Kill Session", "Are you sure to kill session %d?"%session_id,
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        node = etree.Element("kill-session")
        etree.SubElement(node, "session-id").text = str(session_id)
        rply = self.session.setCommandXML(to_xml(node), True)
        if rply.error:
            QMessageBox.warning(self, "Warning", "%s"%rply.error.message)

        self._onRefreshInfo()

    def getSessionInfo(self):
        "获取会话信息"
        filter=('subtree', '<netconf-state xmlns="urn:ietf:params:xml:ns:yang:ietf-netconf-monitoring"><sessions/></netconf-state>')
        try:
            send_time = QDateTime.currentDateTime()
            rpc, req = self.session._proxy.get(filter)
            self.session._sessionHistory.appendHistory(send_time, SessionOperType.Out, req)
            session_rpy = self.session._proxy.wait_asnync_reply(rpc)
            cur_time = QDateTime.currentDateTime()
            timediff = '{:,}'.format(send_time.msecsTo(cur_time))
            self.session._sessionHistory.appendHistory(cur_time, SessionOperType.In, session_rpy.xml, extra=f'(took {timediff} ms)')
        except Exception as ex:
            log.error("GetSession err: %s"%str(ex))
            return []
        else:
            data = session_rpy.data
            if data == None :
                log.error("get sesson list error: %s", session_rpy.xml)
                return []
            session_list=[]
            for netconf_state in etree.ElementChildIterator(data):
                for sessions in etree.ElementChildIterator(netconf_state):
                    for session in etree.ElementChildIterator(sessions):
                        info = {}
                        for leaf in etree.ElementChildIterator(session):
                            tag = etree.QName(leaf).localname
                            info[tag] = leaf.text
                        session_list.append(info)
            log.debug("sesion_list:%s", session_list)
            return session_list

    def killSession(self, session_id: int):
        "kill 会话"
        pass

if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d: %(message)s',
                level=logging.DEBUG)

    app = QApplication(sys.argv)
    # widget = SchemaWidgets()
    # widget.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, True)
    # widget.show()

    # cap = CapabilityWidgets()
    # widget.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, True)
    # cap.show()

    # dlg = CallHomeDialog({})

    # dlg = CopyConfiguration()
    # dlg = DeleteConfiguration()
    # dlg = ComfirmedCommit()
    # dlg = CancelComfirmedCommit()
    # dlg = ValidateConfiguration()
    # dlg = LockUnlockDatastore()
    nt = """<notification xmlns="urn:ietf:params:xml:ns:netconf:notification:1.0">
  <eventTime>2023-08-12T11:15:22Z</eventTime>
  <running-config-notification xmlns="urn:rg:params:xml:ns:yang:rg-configd">
    <running-config>
      <update-time>1691838922961</update-time>
    </running-config>
  </running-config-notification>
</notification>"""
    # dlg = NotificationWidget()

    # timer = QTimer()
    # timer.setInterval(1000*1)
    # timer.timeout.connect(lambda: dlg.appendNotification(nt))
    # timer.start()

    # dlg.appendNotification(nt)
    # dlg.appendNotification(nt1)
    # dlg.appendNotification(nt2)
    # for i in range(1, 10000):
    #     dlg.appendNotification(nt)
    #     dlg.appendNotification(nt1)
    #     dlg.appendNotification(nt2)
    dlg = SessionManager()
    dlg.show()
    sys.exit(app.exec())