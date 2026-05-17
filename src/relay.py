import asyncio
import websockets
import json
import random
import string
import traceback

# Storage for pending and active connections
codes = {} # code -> host_ws
pairs = {} # ws -> target_ws

def get_state(ws):
    try:
        return str(ws.state)
    except:
        return "UNKNOWN"

def is_open(ws):
    """Check if the connection is open according to websockets 14+ API"""
    try:
        # In websockets 14+, .state is an Enum. State.OPEN is the value for open connection.
        return ws.state == websockets.State.OPEN
    except:
        # Fallback for older versions or if attribute missing
        try:
            return not ws.closed
        except:
            return False

async def handle_connection(websocket):
    addr = str(websocket.remote_address)
    print(f"[{addr}] New connection. State: {get_state(websocket)}")
    
    current_code = None
    role = "unknown"

    try:
        async for message in websocket:
            # 1. Handle Binary (Video frames)
            if isinstance(message, bytes):
                target = pairs.get(websocket)
                if is_open(target):
                    await target.send(message)
                continue

            # 2. Handle Text (Commands)
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                # If not JSON, try to forward if paired (though everything should be JSON)
                target = pairs.get(websocket)
                if is_open(target):
                    await target.send(message)
                continue

            msg_type = data.get("type")

            if msg_type == "register_host":
                role = "host"
                while True:
                    code = ''.join(random.choices(string.digits, k=6))
                    if code not in codes:
                        break
                current_code = code
                codes[code] = websocket
                print(f"[{addr}] Host registered with code: {code}")
                await websocket.send(json.dumps({"type": "registration_success", "code": code}))

            elif msg_type == "join_client":
                role = "client"
                code = data.get("code")
                print(f"[{addr}] Client trying to join code: {code}")
                
                if code in codes:
                    host_ws = codes[code]
                    if is_open(host_ws):
                        # Map client to host
                        pairs[websocket] = host_ws
                        print(f"[{addr}] Found host for code {code}. Requesting connection...")
                        await host_ws.send(json.dumps({
                            "type": "connection_request", 
                            "client_id": addr
                        }))
                    else:
                        print(f"[{addr}] Host for code {code} is not open (State: {get_state(host_ws)})")
                        if code in codes: del codes[code]
                        await websocket.send(json.dumps({"type": "error", "message": "Host disconnected"}))
                else:
                    print(f"[{addr}] Invalid code attempted: {code}")
                    await websocket.send(json.dumps({"type": "error", "message": "Invalid code"}))

            elif msg_type == "accept_connection":
                if role == "host":
                    # Find the client that is mapped to this host
                    client_ws = None
                    for c_ws, h_ws in list(pairs.items()):
                        if h_ws == websocket:
                            client_ws = c_ws
                            break
                    
                    if is_open(client_ws):
                        # Map host to client (for bidirectional)
                        pairs[websocket] = client_ws
                        print(f"[{addr}] Host accepted client {client_ws.remote_address}. Pairing complete.")
                        await client_ws.send(json.dumps({"type": "connection_accepted"}))
                    else:
                        print(f"[{addr}] Could not find open client to accept.")
                        await websocket.send(json.dumps({"type": "error", "message": "Client lost"}))
            
            else:
                # Forward other JSON (Input events)
                target = pairs.get(websocket)
                if is_open(target):
                    await target.send(message)

    except websockets.exceptions.ConnectionClosed as e:
        print(f"[{addr}] Connection closed: {e}")
    except Exception as e:
        print(f"[{addr}] Relay Error: {e}")
        traceback.print_exc()
    finally:
        # Cleanup
        if role == "host":
            if current_code in codes: del codes[current_code]
            client_ws = pairs.pop(websocket, None)
            # Find any clients pointing to this host
            to_remove = []
            for c_ws, h_ws in pairs.items():
                if h_ws == websocket:
                    to_remove.append(c_ws)
            for c_ws in to_remove:
                del pairs[c_ws]
                try: await c_ws.close()
                except: pass
        elif role == "client":
            host_ws = pairs.pop(websocket, None)
            if is_open(host_ws):
                try:
                    await host_ws.send(json.dumps({"type": "client_disconnected"}))
                    # Remove host's mapping to this client
                    if pairs.get(host_ws) == websocket:
                        del pairs[host_ws]
                except: pass

async def main():
    port = 8765
    print(f"Relay (Pairing v4) starting on port {port}...")
    async with websockets.serve(handle_connection, "0.0.0.0", port):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
