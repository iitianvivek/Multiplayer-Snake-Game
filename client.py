#!/usr/bin/env python3
"""
Simple ASCII client for the Multiplayer Snake server.
"""
import sys
import socket
import threading
import json
import argparse
import time

# --- CROSS-PLATFORM INPUT HANDLING ---
# This section detects the Operating System to define a 'getch()' function.
# 'getch' reads a single character from the keyboard WITHOUT waiting for Enter.

try:
   
    import msvcrt
    def getch():
        # msvcrt.getwch() is a standard Windows function to read a wide char
        return msvcrt.getwch()
except ImportError:

    # We must use the 'termios' and 'tty' libraries to change terminal settings.
    import tty
    import termios
    def getch():
        fd = sys.stdin.fileno()
        # Save old settings so we can restore them later (clean exit)
        old = termios.tcgetattr(fd)
        try:
            # Set terminal to "Raw Mode" (disable buffering and echoing)
            tty.setraw(fd)
            # Read exactly 1 byte
            ch = sys.stdin.read(1)
            return ch
        finally:
            # Restore terminal to normal (Cooked Mode)
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def clear():
    """
    Clears the terminal screen using ANSI escape codes.
    \x1b[2J = Clear entire screen
    \x1b[H  = Move cursor to top-left (Home)
    """
    sys.stdout.write('\x1b[2J\x1b[H')


class Client:
    def __init__(self, host='127.0.0.1', port=8765):
        self.host = host
        self.port = port
        self.sock = None
        self.running = True
        self.last_frame = None

    def connect(self):
        """
        Establishes connection and starts the threads.
        """
        try:
            # Create a standard TCP socket
            self.sock = socket.create_connection((self.host, self.port))
            # Wrap socket in a file object for easier reading (readline)
            self.sock_file = self.sock.makefile('rwb')
            
            # --- START LISTENER THREAD ---
            # We create a separate thread just to listen for server updates.
            # daemon=True means this thread dies when the main program dies.
            t = threading.Thread(target=self.listen_loop, daemon=True)
            t.start()
            
            # --- START INPUT LOOP (Main Thread) ---
            # The main thread stays here to handle keyboard input.
            self.input_loop()
            
        except KeyboardInterrupt:
            # User pressed Ctrl+C
            self.running = False
            print('\nExiting...')
        finally:
            # Clean up the socket connection
            try:
                self.sock.close()
            except Exception:
                pass

    def listen_loop(self):
        """
        Runs in a background thread.
        Constantly waits for data from the Server.
        """
        f = self.sock_file
        while self.running:
            try:
                # This line BLOCKS until the server sends a line ending in \n
                line = f.readline()
                if not line:
                    break # Connection closed by server
                
                # Parse the incoming JSON
                msg = json.loads(line.decode('utf8').strip())
            except Exception:
                continue # Skip malformed packets

            # Handle Message Types
            if msg.get('type') == 'frame':
                # This is a game update (map state)
                self.last_frame = msg
                self.render(msg)
            elif msg.get('type') == 'dead':
                # Server told us we died
                print(f"You died (pid {msg.get('pid')})")
                # We don't exit here, we just keep watching the game (spectator mode)

    def render(self, frame):
        """
        Draws the game board.
        """
        # 1. Clear the terminal
        clear()
        # 2. Print the rows received from server
        rows = frame['rows']
        print('\n'.join(rows))
        print('\nControls: WASD keys (or arrow keys) to move. Ctrl-C to quit.')

    def send_dir(self, d):
        """
        Sends a move command to the server.
        Format: {"type": "cmd", "dir": "U"}
        """
        msg = {'type':'cmd', 'dir':d}
        try:
            # Write JSON followed by newline
            self.sock_file.write((json.dumps(msg) + '\n').encode('utf8'))
            # Flush ensures data is sent immediately, not buffered
            self.sock_file.flush()
        except Exception:
            self.running = False

    def input_loop(self):
        """
        Runs in the Main Thread.
        Constantly waits for keyboard presses.
        """
        while self.running:
            # getch() blocks until a key is pressed
            ch = getch()
            if not ch:
                continue
            
            # Normalize input
            if isinstance(ch, bytes):
                ch = ch.decode('utf-8', errors='ignore')
            ch = ch.lower()

            # Mapping keys to Server Directions ('U', 'D', 'L', 'R')
            # We handle both WASD and Arrow Keys (ANSI Escape codes)
            if ch == 'w' or ch == '\x1b[A':   # Up
                self.send_dir('U')
            elif ch == 's' or ch == '\x1b[B': # Down
                self.send_dir('D')
            elif ch == 'a' or ch == '\x1b[D': # Left
                self.send_dir('L')
            elif ch == 'd' or ch == '\x1b[C': # Right
                self.send_dir('R')
            
            # Tiny sleep prevents CPU spiking to 100% in some tight loop scenarios
            time.sleep(0.01)


if __name__ == '__main__':
    # Parse command line arguments (optional host/port)
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=8765, type=int)
    args = parser.parse_args()
    
    # Start the client
    c = Client(args.host, args.port)
    c.connect()