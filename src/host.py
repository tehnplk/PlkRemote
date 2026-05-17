import sys
import asyncio
import json
import dxcam
import cv2
import websockets
import qasync
import win32api
import win32con
import ctypes
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal

# Set DPI awareness for precise mouse control
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

class HostWindow(QMainWindow):
    connection_requested = pyqtSignal(str)
    
    def __init__(self, relay_ip, port):
        super().__init__()
        self.relay_ip = relay_ip
        self.port = port
        self.url = f"ws://{relay_ip}:{port}"
        
        self.setWindowTitle("PlkRemote Host")
        self.setFixedSize(300, 200)
        
        self.code_label = QLabel("Connecting to Relay...")
        self.code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_label.setStyleSheet("font-size: 24px; font-weight: bold; color: blue;")
        
        self.status_label = QLabel("Status: Idle")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Your Pairing Code:"))
        layout.addWidget(self.code_label)
        layout.addWidget(self.status_label)
        
        container = QWidget()
        container.setLayout(layout)
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
        self.is_running = False
        self.is_streaming = False
        event.accept()
        QApplication.instance().quit()

    async def init_camera(self):
        while self.is_running and self.camera is None:
            try:
                self.camera = await asyncio.to_thread(dxcam.create, output_color="BGR")
                self.status_label.setText("Status: Ready (Camera OK)")
            except Exception as e:
                await asyncio.sleep(5)

    async def start(self):
        asyncio.create_task(self.init_camera())
        await self.relay_connection_loop()

    def move_mouse(self, x_rel, y_rel):
        """Move mouse to a normalized point within the streamed capture."""
        if x_rel is None or y_rel is None:
            return

        x_rel = max(0.0, min(1.0, float(x_rel)))
        y_rel = max(0.0, min(1.0, float(y_rel)))
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

    async def relay_connection_loop(self):
        while self.is_running:
            self.status_label.setText("Status: Connecting to relay...")
            try:
                async with websockets.connect(self.url, ping_interval=20, ping_timeout=20) as websocket:
                    self.websocket = websocket
                    await websocket.send(json.dumps({"type": "register_host"}))
                    
                    async for message in websocket:
                        if not self.is_running: break
                        if isinstance(message, str):
                            data = json.loads(message)
                            msg_type = data.get("type")
                            if msg_type == "registration_success":
                                self.code_label.setText(data.get("code"))
                                self.status_label.setText("Status: Waiting for client...")
                            elif msg_type == "connection_request":
                                self.connection_requested.emit(data.get("client_id"))
                            elif msg_type == "mouse_move":
                                self.move_mouse(data.get("x"), data.get("y"))
                            elif msg_type == "mouse_click":
                                self.click_mouse(data.get("button"), data.get("action"), data.get("x"), data.get("y"))
                            elif msg_type == "key":
                                # Fallback key support (simpler mapping)
                                try:
                                    k = data.get("key")
                                    if len(k) == 1:
                                        vk = win32api.VkKeyScan(k) & 0xff
                                        win32api.keybd_event(vk, 0, 0 if data.get("action") == "down" else win32con.KEYEVENTF_KEYUP, 0)
                                except: pass
            except:
                if self.is_running: await asyncio.sleep(5)

    def on_connection_requested(self, client_id):
        reply = QMessageBox.question(self, "Connection Request", 
                                   f"Client {client_id} wants to connect. Allow?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            asyncio.create_task(self.accept_and_stream())

    async def accept_and_stream(self):
        if self.websocket:
            await self.websocket.send(json.dumps({"type": "accept_connection"}))
            self.status_label.setText("Status: Streaming...")
            self.is_streaming = True
            while self.is_streaming and self.is_running:
                if self.camera:
                    frame = self.camera.grab()
                    if frame is not None:
                        height, width = frame.shape[:2]
                        self.capture_width = width
                        self.capture_height = height
                        _, compressed = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
                        try: await self.websocket.send(compressed.tobytes())
                        except: break
                await asyncio.sleep(0.01)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("relay", nargs="?", default="76.13.182.35")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    host = HostWindow(args.relay, 8765)
    host.show()
    loop.create_task(host.start())
    with loop: loop.run_forever()

if __name__ == "__main__":
    main()
