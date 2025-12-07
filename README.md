# Multiplayer Snake (IPC demo)

This is a simple multiplayer Snake demo using TCP loopback as the IPC mechanism.

Components:
- `server.py` — authoritative game server (asyncio)
- `client.py` — ASCII terminal client (WASD controls)
- `bot.py` — simple automated bot client

Requirements: Python 3.8+

How to run (PowerShell):

```powershell
python .\server.py
# in other terminals:
python .\client.py
python .\bot.py
```

Notes:
- Server broadcasts frames as JSON messages, clients send small JSON commands.
- This is intentionally simple. If you want true shared-memory + semaphores, I can help convert the frame transport to memory-mapped files next.
