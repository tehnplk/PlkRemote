import asyncio
import websockets

async def test_client():
    url = "ws://127.0.0.1:8765"
    try:
        async with websockets.connect(url) as websocket:
            print("Connected to host")
            # Wait for first frame
            message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            if isinstance(message, bytes):
                print(f"Received frame of size: {len(message)} bytes")
            else:
                print(f"Received unexpected text: {message}")
    except Exception as e:
        print(f"Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_client())
