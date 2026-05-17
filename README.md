# PlkRemote - Remote Desktop System

High-performance remote desktop system using Windows DXGI (via `dxcam`) and WebSockets.

## Features
- **High FPS**: Uses `dxcam` for GPU-accelerated screen capture.
- **Low Latency**: JPEG compression and fast WebSocket streaming.
- **Precise Input**: Uses `pydirectinput` for DirectX-compatible input control.
- **Cross-platform Client**: Client runs on any OS with Python/PyQt6 support.

## Requirements
- Python 3.10+
- Windows (for Host)
- `uv` package manager

## Installation
```bash
uv sync
```

## Architecture
The system uses a **Relay/Signaling** architecture to bypass NAT and Firewalls:
1. **Relay Server**: A central point where both Host and Client connect.
2. **Host**: Connects to the Relay and waits for a Client to join.
3. **Client**: Connects to the Relay to start controlling the Host.

### 1. Start Relay (on a public server)
```bash
uv run src/relay.py
```

### 2. Start Host (on the machine to be controlled)
```bash
uv run src/host.py <RELAY_IP>
```

### 3. Start Client (on the controlling machine)
```bash
uv run src/client.py <RELAY_IP>
```

## Building EXE
To build a standalone executable for the Host:
```bash
uv run pyinstaller --onefile --noconsole src/host.py
```
To build for the Client:
```bash
uv run pyinstaller --onefile --noconsole src/client.py
```

## Troubleshooting
- **TurboJPEG**: If you see "Falling back to OpenCV", it means `libturbojpeg` is not installed. You can download it from [libjpeg-turbo.org](https://libjpeg-turbo.org/) and place the DLL in your system path for even better performance.
