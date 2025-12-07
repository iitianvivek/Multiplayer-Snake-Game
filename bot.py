#!/usr/bin/env python3
"""
Random-move Bot Client.
Useful for stress-testing the server or simulating other players.
"""
import socket
import json
import random
import time

# --- CONFIGURATION ---
HOST = '127.0.0.1'
PORT = 8765
DIRS = ['U', 'D', 'L', 'R']  # The possible moves

# --- CONNECTION ---
# Bots don't need complex threads because they don't read user input.
# They just write data blindly.
try:
    s = socket.create_connection((HOST, PORT))
    # We create a file-like object mostly for consistency, 
    # though strictly speaking we only need write access here.
    f = s.makefile('rwb')
    print(f"Bot connected to {HOST}:{PORT}")
except ConnectionRefusedError:
    print("Could not connect. Is the server running?")
    exit()

# --- BOT LOOP ---
try:
    while True:
        # 1. Pick a random direction
        # Note: This bot is "dumb". It doesn't check if it's about to hit a wall.
        d = random.choice(DIRS)
        
        # 2. Construct the JSON command
        msg = {'type': 'cmd', 'dir': d}
        
        # 3. Send to Server
        # We encode to UTF-8 bytes and ensure a newline (\n) acts as the delimiter
        try:
            f.write((json.dumps(msg) + '\n').encode('utf8'))
            f.flush() # Force the data out of the buffer immediately
        except BrokenPipeError:
            print("Server disconnected.")
            break

        # 4. Wait
        # We sleep 0.25s. Since the server ticks every 0.20s, 
        # this bot changes direction roughly once per tick.
        time.sleep(0.25)

except KeyboardInterrupt:
    print("\nBot stopping...")
finally:
    # Cleanup resources
    try:
        s.close()
    except Exception:
        pass