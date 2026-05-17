| Layer | Stack | Reason |
|-------|-------|--------|
| Screen Capture | `dxcam` or `bettercam` | Uses Windows Desktop Duplication API (DXGI) via GPU, 60-120+ FPS, very low CPU (never use PIL or PyAutoGUI — too slow) |
| Input Control | `pydirectinput` or `pywin32` | Low-level mouse/keyboard signals (DirectX compatible), precise control, not blocked by Windows/Game security |
| Image Compression | `turbojpeg` (PyTurboJPEG) or `lz4` | Fast hardware-accelerated JPEG compression before network send, saves bandwidth |
| Network Streaming | `websockets` + `asyncio` or `Socket.io` | Real-time bidirectional (Full-Duplex) communication |
| User Interface | `PyQt6` + `qasync` | Modern GUI for Host/Client with asyncio integration for non-blocking network/UI updates |
