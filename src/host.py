import sys
import asyncio
import json
import logging
import os
from pathlib import Path
import dxcam
import cv2
import websockets
import qasync
import win32api
import win32con
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QMainWindow, QLabel, QVBoxLayout, QWidget, QMessageBox
from PyQt6.QtCore import QEvent, Qt, pyqtSignal

TARGET_FPS = 30
JPEG_QUALITY = 45
MAX_FRAME_WIDTH = 1280

def configure_logging():
    log_root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PlkRemote"
    log_root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_root / "host.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

APP_STYLE = """
QMainWindow {
    background: #f4f7fb;
}
QLabel {
    color: #172033;
    font-family: "Segoe UI";
}
QFrame#panel {
    background: #ffffff;
    border: 1px solid #dbe3ee;
    border-radius: 8px;
}
QLabel#eyebrow {
    color: #607086;
    font-size: 11px;
    font-weight: 600;
}
QLabel#title {
    color: #101827;
    font-size: 20px;
    font-weight: 700;
}
QLabel#subtle {
    color: #607086;
    font-size: 12px;
}
QLabel#code {
    background: #eef5ff;
    border: 1px solid #b8d3ff;
    border-radius: 8px;
    color: #0b4db3;
    font-size: 34px;
    font-weight: 700;
    padding: 16px 18px;
}
QLabel#status {
    background: #f7f9fc;
    border: 1px solid #e0e7f1;
    border-radius: 8px;
    color: #32435a;
    font-size: 13px;
    padding: 10px 12px;
}
QLabel#badge {
    background: #eaf3ff;
    border: 1px solid #c7ddff;
    border-radius: 8px;
    color: #1756aa;
    font-size: 11px;
    font-weight: 700;
    padding: 5px 9px;
}
"""

REMOTE_KEY_TO_VK = {
    "shift": win32con.VK_SHIFT,
    "ctrl": win32con.VK_CONTROL,
    "control": win32con.VK_CONTROL,
    "alt": win32con.VK_MENU,
    "win": getattr(win32con, "VK_LWIN", 0x5B),
    "caplock": win32con.VK_CAPITAL,
    "capslock": win32con.VK_CAPITAL,
    "esc": win32con.VK_ESCAPE,
    "escape": win32con.VK_ESCAPE,
    "tab": win32con.VK_TAB,
    "enter": win32con.VK_RETURN,
    "return": win32con.VK_RETURN,
    "backspace": win32con.VK_BACK,
    "delete": win32con.VK_DELETE,
    "insert": win32con.VK_INSERT,
    "home": win32con.VK_HOME,
    "end": win32con.VK_END,
    "pageup": win32con.VK_PRIOR,
    "pagedown": win32con.VK_NEXT,
    "left": win32con.VK_LEFT,
    "right": win32con.VK_RIGHT,
    "up": win32con.VK_UP,
    "down": win32con.VK_DOWN,
    "space": win32con.VK_SPACE,
}

for index in range(1, 13):
    REMOTE_KEY_TO_VK[f"f{index}"] = getattr(win32con, f"VK_F{index}")

EXTENDED_KEYS = {
    win32con.VK_MENU,
    getattr(win32con, "VK_LWIN", 0x5B),
    win32con.VK_INSERT,
    win32con.VK_DELETE,
    win32con.VK_HOME,
    win32con.VK_END,
    win32con.VK_PRIOR,
    win32con.VK_NEXT,
    win32con.VK_LEFT,
    win32con.VK_RIGHT,
    win32con.VK_UP,
    win32con.VK_DOWN,
}

def qt_args():
    if sys.platform == "win32" and "-platform" not in sys.argv:
        return [sys.argv[0], "-platform", "windows:dpiawareness=0", *sys.argv[1:]]
    return sys.argv

class HostWindow(QMainWindow):
    connection_requested = pyqtSignal(str)
    
    def __init__(self, relay_ip, port):
        super().__init__()
        self.relay_ip = relay_ip
        self.port = port
        self.url = f"ws://{relay_ip}:{port}"
        
        self.setStyleSheet(APP_STYLE)
        self.setWindowTitle("PlkRemote Host")
        self.setFixedSize(420, 300)

        header = QHBoxLayout()
        header.setSpacing(12)

        title_stack = QVBoxLayout()
        title_stack.setSpacing(2)
        title = QLabel("PlkRemote")
        title.setObjectName("title")
        subtitle = QLabel("Host station")
        subtitle.setObjectName("subtle")
        title_stack.addWidget(title)
        title_stack.addWidget(subtitle)

        badge = QLabel("HOST")
        badge.setObjectName("badge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header.addLayout(title_stack, 1)
        header.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        code_caption = QLabel("PAIRING CODE")
        code_caption.setObjectName("eyebrow")

        self.code_label = QLabel("----")
        self.code_label.setObjectName("code")
        self.code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.status_label = QLabel("Status: Idle")
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(14)
        layout.addLayout(header)
        layout.addSpacing(4)
        layout.addWidget(code_caption)
        layout.addWidget(self.code_label)
        layout.addWidget(self.status_label)
        panel.setLayout(layout)
        
        container = QWidget()
        outer = QVBoxLayout()
        outer.setContentsMargins(18, 18, 18, 18)
        outer.addWidget(panel)
        container.setLayout(outer)
        self.setCentralWidget(container)
        
        self.websocket = None
        self.camera = None
        self.is_running = True
        self.is_streaming = False
        
        # dxcam captures one output by default. Keep mouse coordinates in the
        # same coordinate space as the streamed frame, not the virtual desktop.
        self.capture_left = 0
        self.capture_top = 0
        self.capture_width = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
        self.capture_height = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)

        self.connection_requested.connect(self.on_connection_requested)

    def closeEvent(self, event):
        logging.info("Host window close requested")
        self.is_running = False
        self.is_streaming = False
        self.stop_camera()
        event.accept()
        QApplication.instance().quit()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            logging.info("Host window state changed: minimized=%s streaming=%s", self.isMinimized(), self.is_streaming)
            if self.isMinimized() and self.is_streaming:
                self.status_label.setText("Status: Streaming in background...")

    async def init_camera(self):
        while self.is_running and self.camera is None:
            try:
                self.camera = await asyncio.to_thread(dxcam.create, output_color="BGR")
                self.status_label.setText(f"Status: Ready (Low latency {TARGET_FPS} FPS)")
                logging.info("Camera initialized")
            except Exception as e:
                logging.exception("Camera initialization failed")
                self.stop_camera()
                await asyncio.sleep(5)

    async def start(self):
        asyncio.create_task(self.init_camera())
        await self.relay_connection_loop()

    def move_mouse(self, x_rel, y_rel):
        """Move mouse to a normalized point within the streamed capture."""
        if x_rel is None or y_rel is None:
            return

        try:
            x_rel = max(0.0, min(1.0, float(x_rel)))
            y_rel = max(0.0, min(1.0, float(y_rel)))
        except (TypeError, ValueError):
            return
        x = int(self.capture_left + (x_rel * max(0, self.capture_width - 1)))
        y = int(self.capture_top + (y_rel * max(0, self.capture_height - 1)))
        win32api.SetCursorPos((x, y))

    def click_mouse(self, button, action, x_rel=None, y_rel=None):
        """Click mouse using win32api"""
        self.move_mouse(x_rel, y_rel)

        flags = 0
        if button == "left":
            flags = win32con.MOUSEEVENTF_LEFTDOWN if action == "down" else win32con.MOUSEEVENTF_LEFTUP
        elif button == "right":
            flags = win32con.MOUSEEVENTF_RIGHTDOWN if action == "down" else win32con.MOUSEEVENTF_RIGHTUP
        
        if flags:
            win32api.mouse_event(flags, 0, 0, 0, 0)

    def press_key(self, key, action):
        vk = self.key_to_vk(key)
        if vk is None:
            return

        flags = 0
        if action == "up":
            flags |= win32con.KEYEVENTF_KEYUP
        if vk in EXTENDED_KEYS:
            flags |= win32con.KEYEVENTF_EXTENDEDKEY

        scan = win32api.MapVirtualKey(vk, 0)
        win32api.keybd_event(vk, scan, flags, 0)

    def key_to_vk(self, key):
        if not key:
            return None

        key = str(key).lower()
        if len(key) == 1:
            if "a" <= key <= "z":
                return ord(key.upper())
            if "0" <= key <= "9":
                return ord(key)
            vk = win32api.VkKeyScan(key) & 0xff
            return vk if vk != 0xff else None

        return REMOTE_KEY_TO_VK.get(key)

    async def relay_connection_loop(self):
        while self.is_running:
            self.status_label.setText("Status: Connecting to relay...")
            try:
                logging.info("Connecting to relay %s", self.url)
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=20) as websocket:
                    self.websocket = websocket
                    await websocket.send(json.dumps({"type": "register_host"}))
                    logging.info("Relay connected and host registered")
                    
                    async for message in websocket:
                        if not self.is_running: break
                        if isinstance(message, str):
                            data = json.loads(message)
                            msg_type = data.get("type")
                            if msg_type == "registration_success":
                                self.code_label.setText(data.get("code"))
                                self.status_label.setText("Status: Waiting for client...")
                                logging.info("Pairing code received")
                            elif msg_type == "connection_request":
                                logging.info("Connection request received from %s", data.get("client_id"))
                                self.connection_requested.emit(data.get("client_id"))
                            elif msg_type == "mouse_move":
                                self.move_mouse(data.get("x"), data.get("y"))
                            elif msg_type == "mouse_click":
                                self.click_mouse(data.get("button"), data.get("action"), data.get("x"), data.get("y"))
                            elif msg_type == "key":
                                self.press_key(data.get("key"), data.get("action"))
                            elif msg_type == "client_disconnected":
                                logging.info("Client disconnected")
                                self.is_streaming = False
                                self.status_label.setText("Status: Waiting for client...")
            except Exception:
                logging.exception("Relay connection loop failed")
                if self.is_running:
                    await asyncio.sleep(5)

    def on_connection_requested(self, client_id):
        reply = QMessageBox.question(self, "Connection Request", 
                                   f"Client {client_id} wants to connect. Allow?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            logging.info("Connection request accepted")
            asyncio.create_task(self.accept_and_stream())
        else:
            logging.info("Connection request rejected")

    async def accept_and_stream(self):
        if self.websocket:
            await self.websocket.send(json.dumps({"type": "accept_connection"}))
            self.status_label.setText("Status: Streaming...")
            logging.info("Streaming started")
            self.is_streaming = True
            frame_interval = 1 / TARGET_FPS

            while self.is_streaming and self.is_running:
                started_at = asyncio.get_running_loop().time()
                if not self.camera:
                    await asyncio.sleep(0.02)
                    continue

                encoded = await asyncio.to_thread(self.capture_and_encode_frame)
                if encoded is not None:
                    try:
                        await self.websocket.send(encoded)
                    except Exception:
                        logging.exception("Frame send failed")
                        break

                elapsed = asyncio.get_running_loop().time() - started_at
                await asyncio.sleep(max(0.001, frame_interval - elapsed))

            self.is_streaming = False
            logging.info("Streaming stopped")

    def capture_and_encode_frame(self):
        if not self.camera:
            return None

        try:
            frame = self.camera.grab()
        except Exception:
            logging.exception("Camera grab failed")
            return None

        if frame is None:
            return None

        height, width = frame.shape[:2]
        self.capture_width = width
        self.capture_height = height

        if width > MAX_FRAME_WIDTH:
            scale = MAX_FRAME_WIDTH / width
            try:
                frame = cv2.resize(
                    frame,
                    (MAX_FRAME_WIDTH, int(height * scale)),
                    interpolation=cv2.INTER_AREA,
                )
            except Exception:
                return None

        try:
            ok, compressed = cv2.imencode(
                ".jpg",
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY],
            )
        except Exception:
            return None
        return compressed.tobytes() if ok else None

    def stop_camera(self):
        camera = self.camera
        self.camera = None
        if not camera:
            return
        try:
            if getattr(camera, "is_capturing", False):
                camera.stop()
        except Exception:
            pass
        try:
            camera.release()
        except Exception:
            pass

def main():
    configure_logging()
    logging.info("Host app starting")
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("relay", nargs="?", default="76.13.182.35")
    args = parser.parse_args()
    app = QApplication(qt_args())
    app.setQuitOnLastWindowClosed(False)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    host = HostWindow(args.relay, 8765)
    host.show()
    loop.create_task(host.start())
    with loop: loop.run_forever()

if __name__ == "__main__":
    main()
