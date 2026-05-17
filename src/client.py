import sys
import asyncio
import json
import qasync
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget, QLineEdit, QPushButton
from PyQt6.QtGui import QImage, QPixmap, QMouseEvent, QKeyEvent
from PyQt6.QtCore import Qt, QEvent
import websockets

class ClientWindow(QMainWindow):
    def __init__(self, relay_ip, port):
        super().__init__()
        self.relay_ip = relay_ip
        self.port = port
        self.url = f"ws://{relay_ip}:{port}"
        
        self.setWindowTitle("PlkRemote Client")
        self.resize(400, 300)
        
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
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("Enter 6-digit Pairing Code:"))
        self.code_input = QLineEdit()
        self.code_input.setMaxLength(6)
        self.code_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_input.setStyleSheet("font-size: 20px;")
        layout.addWidget(self.code_input)
        
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.start_connection)
        layout.addWidget(self.connect_btn)
        
        self.status_label = QLabel("Status: Ready")
        layout.addWidget(self.status_label)
        
        self.central_widget.setLayout(layout)

    def setup_display_ui(self):
        self.display_label = QLabel("Waiting for screen...")
        self.display_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.display_label.setStyleSheet("background-color: black;")
        self.setCentralWidget(self.display_label)
        self.display_label.setMouseTracking(True)
        self.display_label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.display_label.installEventFilter(self)
        self.display_label.setFocus()
        self.resize(1280, 720)

    def start_connection(self):
        code = self.code_input.text()
        if len(code) == 6:
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
        scaled = pixmap.scaled(self.display_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
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
        if e.text():
            self.send_event({"type": "key", "key": e.text(), "action": action})

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

    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    client = ClientWindow(args.relay, 8765)
    client.show()
    
    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()
