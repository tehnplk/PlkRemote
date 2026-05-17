import asyncio
import websockets
import json
import sys

async def test_host_cli():
    relay_url = "ws://76.13.182.35:8765"
    print(f"--- CLI Host Test ---")
    print(f"Connecting to relay: {relay_url}")
    
    try:
        async with websockets.connect(relay_url) as ws:
            print("Connected. Sending 'register_host'...")
            await ws.send(json.dumps({"type": "register_host"}))
            
            # Wait for registration success
            response = await ws.recv()
            data = json.loads(response)
            
            if data.get("type") == "registration_success":
                code = data.get("code")
                print(f"SUCCESS! Host Registered.")
                print(f"Your 4-digit code is: {code}")
                print("The relay is working and the host protocol is correct.")
            else:
                print(f"FAILED: Unexpected response: {data}")
                
    except Exception as e:
        print(f"ERROR: Could not connect to relay: {e}")

if __name__ == "__main__":
    asyncio.run(test_host_cli())
