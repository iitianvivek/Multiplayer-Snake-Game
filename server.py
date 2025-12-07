#!/usr/bin/env python3
import asyncio
import json
import random
import time

# --- CONFIGURATION ---
WIDTH = 30       # The width of the game grid
HEIGHT = 15      # The height of the game grid
TICK = 0.2       # Time in seconds between updates (lower = faster game)

# Dictionary mapping direction keys to (x, y) coordinate changes
DIRS = {
    'U': (0, -1), # Up decreases Y
    'D': (0, 1),  # Down increases Y
    'L': (-1, 0), # Left decreases X
    'R': (1, 0),  # Right increases X
}

class Snake:
    """
    Represents a single player's snake.
    """
    def __init__(self, pid, x, y, dir_key):
        self.pid = pid              # Unique Player ID
        self.body = [(x, y)]        # List of coordinates. body[0] is the Head.
        self.dir = dir_key          # Current direction ('U', 'D', 'L', 'R')
        self.grow = 0               # Counter: how many segments to add (from eating food)
        self.alive = True           # Status flag

class Server:
    def __init__(self, host='127.0.0.1', port=8765):
        self.host = host
        self.port = port
        
        # --- STATE MANAGEMENT ---
        self.players = {}  # Maps the TCP reader object -> Player ID
        self.writers = {}  # Maps Player ID -> TCP writer object (to send data)
        self.snakes = {}   # Maps Player ID -> Snake Object
        self.next_pid = 1  # ID counter for new players
        self.food = set()  # A set of (x, y) tuples for food locations
        
        # Asyncio Lock: Crucial for preventing race conditions.
        # It ensures we don't calculate game physics while a new player 
        # is trying to join or leave at the exact same moment.
        self.lock = asyncio.Lock()

    async def start(self):
        """
        Starts the TCP server and the game loop.
        """
        # Create the TCP server handler
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
        print(f"Server listening on {self.host}:{self.port}")
        
        # Create some initial food
        for _ in range(10):
            self.spawn_food()
            
        # Start the background task that updates physics (The Game Loop)
        asyncio.create_task(self.tick_loop())
        
        # Keep the server running forever
        async with self.server:
            await self.server.serve_forever()

    def spawn_food(self):
        """
        Finds a random empty spot to place food.
        """
        while True:
            x = random.randrange(WIDTH)
            y = random.randrange(HEIGHT)
            # Check if spot is occupied by a snake
            if any((x, y) in s.body for s in self.snakes.values()):
                continue
            # Check if spot already has food
            if (x, y) in self.food:
                continue
            self.food.add((x, y))
            break

    async def handle_client(self, reader, writer):
        """
        Runs dedicatedly for EACH connected client.
        Handles receiving input (Key presses).
        """
        pid = self.next_pid
        self.next_pid += 1
        addr = writer.get_extra_info('peername')
        print(f"Client {pid} connected from {addr}")

        # --- INITIALIZATION ---
        # Pick a random start spot
        x = random.randrange(WIDTH)
        y = random.randrange(HEIGHT)
        snake = Snake(pid, x, y, random.choice(list(DIRS.keys())))

        # Safely add the new player to the shared dictionaries
        async with self.lock:
            self.snakes[pid] = snake
            self.writers[pid] = writer
            self.players[reader] = pid

        # --- INPUT LOOP ---
        try:
            while True:
                # Wait for data from this specific client
                line = await reader.readline()
                if not line:
                    break # Client disconnected

                # Parse JSON command. Expecting: {"type":"cmd", "dir":"U"}
                try:
                    msg = json.loads(line.decode('utf8').strip())
                except Exception:
                    continue # Ignore garbage data

                if msg.get('type') == 'cmd':
                    d = msg.get('dir')
                    if d in DIRS:
                        async with self.lock:
                            s = self.snakes.get(pid)
                            if s and s.alive:
                                # Logic to prevent 180-degree turns (suicide turns)
                                # If snake is moving Up, it cannot immediately go Down.
                                if len(s.body) < 2:
                                    s.dir = d
                                else:
                                    hx, hy = s.body[0] # Head
                                    nx, ny = s.body[1] # Neck (segment after head)
                                    # If the new direction doesn't point back to the neck, it's valid
                                    if (hx - nx, hy - ny) != DIRS[d]:
                                        s.dir = d

        except asyncio.CancelledError:
            pass # Task was cancelled (server shutdown)
        finally:
            # --- CLEANUP ---
            # If loop exits, client is gone. Remove them.
            print(f"Client {pid} disconnected")
            async with self.lock:
                if pid in self.snakes:
                    self.snakes[pid].alive = False
                if pid in self.writers:
                    del self.writers[pid]

    async def tick_loop(self):
        """
        The 'Heartbeat' of the game. Runs X times per second.
        """
        while True:
            start = time.time()
            
            # Lock state, calculate new positions, and send updates
            async with self.lock:
                self.game_tick()
                await self.broadcast_frame()
            
            # Calculate how long the calculations took, and sleep for the remainder of the TICK
            # to maintain a steady framerate.
            elapsed = time.time() - start
            await asyncio.sleep(max(0, TICK - elapsed))

    def game_tick(self):
        """
        Calculates physics: Movement, Collisions, Growth.
        """
        to_kill = [] # List of pids to remove this turn

        for pid, s in list(self.snakes.items()):
            if not s.alive:
                continue

            # 1. Calculate new Head Position
            dx, dy = DIRS[s.dir]
            hx, hy = s.body[0]
            nx, ny = hx + dx, hy + dy

            # 2. Wrap around screen edges (Toroidal grid)
            nx %= WIDTH
            ny %= HEIGHT
            head = (nx, ny)

            # 3. Check Collisions (Self or Other Snakes)
            collision = False
            for other in self.snakes.values():
                if not other.alive: continue
                if head in other.body:
                    # Special logic: If hitting own tail and tail is about to move away, it's safe.
                    # Otherwise, it's a crash.
                    collision = True
                    break
            
            if collision:
                s.alive = False
                to_kill.append(pid)
                continue

            # 4. Move Snake
            s.body.insert(0, head) # Add new head
            
            # 5. Check Food
            if (nx, ny) in self.food:
                self.food.remove((nx, ny))
                s.grow += 3 # Grow by 3 segments
                self.spawn_food()

            # 6. Handle Tail
            if s.grow > 0:
                s.grow -= 1 # Keep tail (snake gets longer)
            else:
                s.body.pop() # Remove tail (snake stays same length)

        # Notify dead players
        for pid in to_kill:
            if pid in self.writers:
                try:
                    w = self.writers[pid]
                    w.write(json.dumps({'type':'dead','pid':pid}).encode('utf8')+b"\n")
                except Exception:
                    pass

    async def broadcast_frame(self):
        """
        Renders the game state to text and sends it to ALL clients.
        """
        # Create empty grid
        rows = [["."] * WIDTH for _ in range(HEIGHT)]
        
        # Draw Food
        for x, y in list(self.food):
            rows[y][x] = '*'
            
        # Draw Snakes
        for pid, s in self.snakes.items():
            if not s.alive: continue
            # Use last digit of PID as the character (Player 1 -> '1', Player 12 -> '2')
            ch = str(pid % 10) 
            for i, (x, y) in enumerate(s.body):
                # Head is Uppercase, Body is Lowercase
                rows[y][x] = ch if i > 0 else ch.upper()
        
        # Convert list of lists to list of strings
        rows_s = ["".join(r) for r in rows]
        
        # Create JSON payload
        msg = {'type':'frame', 'w':WIDTH, 'h':HEIGHT, 'rows':rows_s}
        data = (json.dumps(msg) + '\n').encode('utf8')

        # Send to everyone
        dead = []
        for pid, w in list(self.writers.items()):
            try:
                w.write(data)
                await w.drain() # Wait for OS to accept data
            except Exception:
                dead.append(pid)
        
        # Clean up connections that dropped during broadcast
        for pid in dead:
            del self.writers[pid]

if __name__ == '__main__':
    s = Server()
    try:
        asyncio.run(s.start())
    except KeyboardInterrupt:
        print("Server shutting down")