import sys
import curses
import random
import asyncio

from asyncsnake import LockstepConsumers, run_coroutines
from cursessnake import CursesCharacters, complex_wrap, wrapper


class GameOver(Exception):
    pass


UP = 0-1j
RIGHT = 1+0j
DOWN = 0+1j
LEFT = -1+0j

BODY = 'X'
FOOD = 'o'

INITIAL_LENGTH = 6


class Screen:
    def __init__(self, stdscr):
        self.board = {}
        self.stdscr = stdscr
        self.stdscr.nodelay(1)
        curses.curs_set(0)
        self.YELLOW = 1
        curses.init_pair(self.YELLOW, curses.COLOR_RED, curses.COLOR_BLACK)

    def addch(self, pos, ch):
        i = int(pos.imag)
        j = int(pos.real)
        self.board[i, j] = ord(ch)
        self.update(i // 2, j)
        assert self.inch(pos) == ord(ch)

    def update(self, row, col):
        ch1 = self.board.get((2*row, col), 0x20)
        ch2 = self.board.get((2*row+1, col), 0x20)
        if ch1 != 0x20 and ch2 != 0x20:
            c = '\N{FULL BLOCK}'
        elif ch1 != 0x20:
            c = '\N{UPPER HALF BLOCK}'
        elif ch2 != 0x20:
            c = '\N{LOWER HALF BLOCK}'
        else:
            c = ' '
        self.stdscr.addch(row, col, c, curses.color_pair(self.YELLOW))

    def move(self, pos):
        i = int(pos.imag)
        j = int(pos.real)
        self.stdscr.move(i // 2, j)

    def inch(self, pos):
        i = int(pos.imag)
        j = int(pos.real)
        return self.board.get((i, j), 0x20)

    def refresh(self):
        self.stdscr.refresh()


def main(stdscr):
    screen = Screen(stdscr)
    addch = screen.addch
    move = screen.move
    inch = screen.inch

    def gettile(pos):
        return chr(inch(pos) & 0xFF)

    player_waiters = {}

    def put_player(snake, pos):
        addch(pos, BODY)
        for f in player_waiters.pop(pos, ()):
            if not f.done():
                f.set_result(snake)

    def wait_for_player(pos):
        f = asyncio.Future()
        player_waiters.setdefault(pos, []).append(f)
        return f

    def random_position():
        return complex(random.randint(0, width-1),
                       random.randint(0, height-1))

    class Snake:
        def __init__(self, pos=None, dir=None, controls=None):
            self.wait = 10
            if pos is None:
                self.pos = 0+0j
            else:
                self.pos = pos
            if dir is None:
                self.prev_dir = self.next_dir = RIGHT
            else:
                self.prev_dir = self.next_dir = dir
            self.steps = 0
            self.tail = [self.pos] * INITIAL_LENGTH
            self.tail_index = 0
            if controls is None:
                controls = [curses.KEY_UP,
                            curses.KEY_LEFT,
                            curses.KEY_DOWN,
                            curses.KEY_RIGHT]
            else:
                controls = [ord(c) if isinstance(c, str)
                            else c for c in controls]
            self.controls = controls

        async def get_directions(self, it):
            async for c in it:
                up, left, down, right = self.controls
                if c == down and self.prev_dir != UP:
                    self.next_dir = 0+1j
                elif c == right and self.prev_dir != LEFT:
                    self.next_dir = 1+0j
                elif c == up and self.prev_dir != DOWN:
                    self.next_dir = 0-1j
                elif c == left and self.prev_dir != RIGHT:
                    self.next_dir = -1+0j

        def step(self):
            addch(self.tail[self.tail_index], ' ')
            self.pos += self.next_dir
            self.pos = complex(self.pos.real % width, self.pos.imag % height)
            self.prev_dir = self.next_dir
            cur_tile = gettile(self.pos)
            if cur_tile == BODY:
                raise GameOver("Boom! You hit yourself")
            self.tail[self.tail_index] = self.pos
            put_player(self, self.pos)
            self.tail_index += 1
            self.steps += 1
            if self.tail_index == len(self.tail):
                self.tail_index = 0

        def on_eat_food(self):
            self.tail.insert(self.tail_index, self.tail[self.tail_index])
            if len(self.tail) == width * height:
                raise GameOver("You win!")

    the_snake = Snake()

    def refresh():
        move(0)
        screen.refresh()

    width = 30
    height = 20

    async def food_loop(pos):
        while True:
            while gettile(pos) != ' ':
                pos = random_position()
            addch(pos, FOOD)
            refresh()
            p = await wait_for_player(pos)
            p.on_eat_food()
            pos = random_position()

    async def faster_loop():
        pos = random_position()
        while True:
            while gettile(pos) != ' ':
                pos = random_position()
            addch(pos, '+')
            refresh()
            p = await wait_for_player(pos)
            if p.wait > 1:
                p.wait -= 1
            pos = random_position()

    async def slower_loop():
        pos = random_position()
        while True:
            while gettile(pos) != ' ':
                pos = random_position()
            addch(pos, '-')
            refresh()
            p = await wait_for_player(pos)
            p.wait += 1
            pos = random_position()

    async def play(snakes):
        t = 0
        n = [0] * len(snakes)
        while True:
            i = min(range(len(snakes)), key=lambda i: n[i])
            if n[i] > t:
                refresh()
                await asyncio.sleep(0.01 * (n[i] - t))
                t = n[i]
            snakes[i].step()
            n[i] += snakes[i].wait

    input = LockstepConsumers()
    snakes = [the_snake, Snake(pos=0+10j, controls='wasd')]
    tasks = [
        input.consume(CursesCharacters(stdscr)),
        food_loop(5+5j),
        faster_loop(),
        slower_loop(),
        play(snakes),
    ]
    for s in snakes:
        tasks.append(
            s.get_directions(input.consumer()))
    try:
        msg = str(run_coroutines(tasks))
    except GameOver as exn:
        msg = exn.args[0]
    except KeyboardInterrupt:
        raise

    raise SystemExit('\n'.join(
        [str(msg),
         "You ate %s foods" % (len(the_snake.tail) - INITIAL_LENGTH),
         "You moved %s tiles" % the_snake.steps,
         "Good job!!"]))


if __name__ == "__main__":
    wrapper(main)
