import sys
import asyncio
import json
import qasync
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QVBoxLayout, QWidget, QLineEdit, QPushButton
from PyQt6.QtGui import QImage, QPixmap, QMouseEvent, QKeyEvent
from PyQt6.QtCore import Qt, QEvent
import websockets

PAIRING_CODE_LENGTH = 4

QT_KEY_NAMES = {
    int(Qt.Key.Key_Shift): "shift",
    int(Qt.Key.Key_Control): "ctrl",
    int(Qt.Key.Key_Alt): "alt",
    int(Qt.Key.Key_Meta): "win",
    int(Qt.Key.Key_CapsLock): "capslock",
    int(Qt.Key.Key_Escape): "esc",
    int(Qt.Key.Key_Tab): "tab",
    int(Qt.Key.Key_Backtab): "tab",
    int(Qt.Key.Key_Return): "enter",
    int(Qt.Key.Key_Enter): "enter",
    int(Qt.Key.Key_Backspace): "backspace",
    int(Qt.Key.Key_Delete): "delete",
    int(Qt.Key.Key_Insert): "insert",
    int(Qt.Key.Key_Home): "home",
    int(Qt.Key.Key_End): "end",
    int(Qt.Key.Key_PageUp): "pageup",
    int(Qt.Key.Key_PageDown): "pagedown",
    int(Qt.Key.Key_Left): "left",
    int(Qt.Key.Key_Right): "right",
    int(Qt.Key.Key_Up): "up",
    int(Qt.Key.Key_Down): "down",
    int(Qt.Key.Key_Space): "space",
}

for index in range(1, 13):
    QT_KEY_NAMES[int(getattr(Qt.Key, f"Key_F{index}"))] = f"f{index}"

APP_STYLE = """
QMainWindow {
    background: #f4f7fb;
}
QLabel, QLineEdit, QPushButton {
    font-family: "Segoe UI";
}
QLabel {
    color: #172033;
}
QFrame#panel {
    background: #ffffff;
    border: 1px solid #dbe3ee;
    border-radius: 8px;
}
QLabel#title {
    color: #101827;
    font-size: 22px;
    font-weight: 700;
}
QLabel#subtle {
    color: #607086;
    font-size: 12px;
}
QLabel#eyebrow {
    color: #607086;
    font-size: 11px;
    font-weight: 600;
}
QLabel#status {
    background: #f7f9fc;
    border: 1px solid #e0e7f1;
    border-radius: 8px;
    color: #32435a;
    font-size: 13px;
    padding: 10px 12px;
}
QLineEdit#codeInput {
    background: #f8fbff;
    border: 1px solid #cfd9e8;
    border-radius: 8px;
    color: #101827;
    font-size: 28px;
    font-weight: 700;
    padding: 14px 16px;
    selection-background-color: #2b6eea;
}
QLineEdit#codeInput:focus {
    border: 1px solid #2b6eea;
    background: #ffffff;
}
QPushButton#primaryButton {
    background: #1f6feb;
    border: 1px solid #1f6feb;
    border-radius: 8px;
    color: #ffffff;
    font-size: 14px;
    font-weight: 700;
    padding: 12px 16px;
}
QPushButton#primaryButton:hover {
    background: #195ec7;
}
QPushButton#primaryButton:pressed {
    background: #124da5;
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
QLabel#display {
    background: #0b1020;
    color: #d6deea;
    font-size: 14px;
}
QFrame#topbar {
    background: #ffffff;
    border-bottom: 1px solid #dbe3ee;
}
"""

def qt_args():
    if sys.platform == "win32" and "-platform" not in sys.argv:
        return [sys.argv[0], "-platform", "windows:dpiawareness=0", *sys.argv[1:]]
    return sys.argv

class ClientWindow(QMainWindow):
    def __init__(self, relay_ip, port):
        super().__init__()
        self.relay_ip = relay_ip
        self.port = port
        self.url = f"ws://{relay_ip}:{port}"
        
        self.setStyleSheet(APP_STYLE)
        self.setWindowTitle("PlkRemote Client")
        self.resize(460, 360)
        
        self.setup_login_ui()
        
        self.websocket = None
        self.display_rect = None
        self.is_running = True

    def closeEvent(self, event):
        self.is_running = False
        event.accept()
        QApplication.instance().quit()

    def setup_login_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        panel = QFrame()
        panel.setObjectName("panel")
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 26, 28, 28)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)
        title_stack = QVBoxLayout()
        title_stack.setSpacing(2)
        title = QLabel("PlkRemote")
        title.setObjectName("title")
        subtitle = QLabel("Client console")
        subtitle.setObjectName("subtle")
        title_stack.addWidget(title)
        title_stack.addWidget(subtitle)

        badge = QLabel("CLIENT")
        badge.setObjectName("badge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header.addLayout(title_stack, 1)
        header.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)
        layout.addSpacing(8)

        code_caption = QLabel("PAIRING CODE")
        code_caption.setObjectName("eyebrow")
        layout.addWidget(code_caption)

        self.code_input = QLineEdit()
        self.code_input.setObjectName("codeInput")
        self.code_input.setMaxLength(PAIRING_CODE_LENGTH)
        self.code_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_input.setPlaceholderText("0000")
        layout.addWidget(self.code_input)
        
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setObjectName("primaryButton")
        self.connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.connect_btn.clicked.connect(self.start_connection)
        layout.addWidget(self.connect_btn)
        
        self.status_label = QLabel("Status: Ready")
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        panel.setLayout(layout)

        outer = QVBoxLayout()
        outer.setContentsMargins(20, 20, 20, 20)
        outer.addWidget(panel)
        self.central_widget.setLayout(outer)

    def setup_display_ui(self):
        self.display_label = QLabel("Waiting for screen...")
        self.display_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.display_label.setObjectName("display")
        self.display_label.setMinimumSize(640, 360)

        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar_layout = QHBoxLayout()
        topbar_layout.setContentsMargins(16, 10, 16, 10)
        topbar_layout.setSpacing(10)
        title = QLabel("PlkRemote Client")
        title.setObjectName("subtle")
        self.session_label = QLabel("Connected")
        self.session_label.setObjectName("badge")
        self.session_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        topbar_layout.addWidget(title, 1)
        topbar_layout.addWidget(self.session_label)
        topbar.setLayout(topbar_layout)

        container = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(topbar)
        layout.addWidget(self.display_label, 1)
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.display_label.setMouseTracking(True)
        self.display_label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.display_label.installEventFilter(self)
        self.display_label.setFocus()
        self.resize(1280, 720)

    def start_connection(self):
        code = self.code_input.text()
        if len(code) == PAIRING_CODE_LENGTH:
            self.status_label.setText("Status: Connecting...")
            # Use the instance loop to create the task
            asyncio.create_task(self.connect_to_relay(code))
        else:
            self.status_label.setText("Status: Invalid code")

    async def connect_to_relay(self, code):
        try:
            print(f"Client connecting to {self.url} with code {code}")
            async with websockets.connect(self.url, ping_interval=20, ping_timeout=20) as websocket:
                self.websocket = websocket
                await websocket.send(json.dumps({"type": "join_client", "code": code}))
                
                async for message in websocket:
                    if not self.is_running: break
                    if isinstance(message, str):
                        data = json.loads(message)
                        if data.get("type") == "connection_accepted":
                            self.setup_display_ui()
                        elif data.get("type") == "error":
                            self.status_label.setText(f"Status: {data.get('message')}")
                    elif isinstance(message, bytes):
                        image = QImage.fromData(message)
                        if not image.isNull():
                            self.update_display(QPixmap.fromImage(image))
        except Exception as e:
            print(f"Client connection error: {e}")
            self.status_label.setText(f"Status: Connection failed")

    def update_display(self, pixmap):
        scaled = pixmap.scaled(
            self.display_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.display_label.setPixmap(scaled)
        w, h = scaled.width(), scaled.height()
        x = (self.display_label.width() - w) // 2
        y = (self.display_label.height() - h) // 2
        self.display_rect = (x, y, w, h)

    def send_event(self, data):
        if self.websocket:
            asyncio.create_task(self.websocket.send(json.dumps(data)))

    def map_coords(self, pos):
        if not self.display_rect: return None
        rx, ry, rw, rh = self.display_rect
        x, y = (pos.x() - rx) / rw, (pos.y() - ry) / rh
        return (x, y) if 0 <= x <= 1 and 0 <= y <= 1 else None

    def eventFilter(self, source, event):
        if source == getattr(self, "display_label", None):
            event_type = event.type()
            if event_type == QEvent.Type.MouseMove:
                self.send_mouse_move(event)
                return True
            if event_type == QEvent.Type.MouseButtonPress:
                self.send_mouse_click(event, "down")
                return True
            if event_type == QEvent.Type.MouseButtonRelease:
                self.send_mouse_click(event, "up")
                return True
            if event_type == QEvent.Type.KeyPress:
                self.send_key(event, "down")
                return True
            if event_type == QEvent.Type.KeyRelease:
                self.send_key(event, "up")
                return True
        return super().eventFilter(source, event)

    def send_mouse_move(self, e: QMouseEvent):
        coords = self.map_coords(e.position())
        if coords:
            self.send_event({"type": "mouse_move", "x": coords[0], "y": coords[1]})

    def send_mouse_click(self, e: QMouseEvent, action):
        coords = self.map_coords(e.position())
        if coords:
            btn = {Qt.MouseButton.LeftButton: "left", Qt.MouseButton.RightButton: "right"}.get(e.button())
            if btn:
                self.send_event({"type": "mouse_click", "button": btn, "action": action, "x": coords[0], "y": coords[1]})

    def send_key(self, e: QKeyEvent, action):
        key = self.remote_key_name(e)
        if key:
            self.send_event({"type": "key", "key": key, "action": action})

    def remote_key_name(self, e: QKeyEvent):
        key_code = int(e.key())
        key_a = int(Qt.Key.Key_A)
        key_z = int(Qt.Key.Key_Z)
        key_0 = int(Qt.Key.Key_0)
        key_9 = int(Qt.Key.Key_9)

        if key_a <= key_code <= key_z:
            return chr(ord("a") + key_code - key_a)

        if key_0 <= key_code <= key_9:
            return chr(ord("0") + key_code - key_0)

        if key_code in QT_KEY_NAMES:
            return QT_KEY_NAMES[key_code]

        text = e.text()
        if len(text) == 1 and text.isprintable():
            return text.lower() if text.isalpha() else text
        return None

    def mouseMoveEvent(self, e: QMouseEvent):
        self.send_mouse_move(e)

    def mousePressEvent(self, e: QMouseEvent):
        self.send_mouse_click(e, "down")

    def mouseReleaseEvent(self, e: QMouseEvent):
        self.send_mouse_click(e, "up")

    def keyPressEvent(self, e: QKeyEvent):
        self.send_key(e, "down")

    def keyReleaseEvent(self, e: QKeyEvent):
        self.send_key(e, "up")

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("relay", nargs="?", default="76.13.182.35")
    args = parser.parse_args()

    app = QApplication(qt_args())
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    client = ClientWindow(args.relay, 8765)
    client.show()
    
    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()
