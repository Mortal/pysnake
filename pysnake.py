import sys
import curses
import random
import asyncio
import functools


class GameOver(Exception):
    pass


def complex_wrap(fn):
    @functools.wraps(fn)
    def wrapped(pos, *args):
        return fn(int(pos.imag), int(pos.real), *args)

    return wrapped


UP = 0-1j
RIGHT = 1+0j
DOWN = 0+1j
LEFT = -1+0j

BODY = 'X'
FOOD = 'o'

INITIAL_LENGTH = 6


def main(stdscr):
    async def getch():
        c = stdscr.getch()
        if c != -1:
            return c

        f = asyncio.Future()

        def on_readable():
            f.set_result(stdscr.getch())

        loop = asyncio.get_event_loop()
        loop.add_reader(sys.stdin, on_readable)
        c = await f
        loop.remove_reader(sys.stdin)
        return c

    class CursesCharacters:
        async def __aiter__(self):
            return self

        async def __anext__(self):
            return await getch()

    addch = complex_wrap(stdscr.addch)
    move = complex_wrap(stdscr.move)
    inch = complex_wrap(stdscr.inch)

    def gettile(pos):
        return chr(inch(pos) & 0xFF)

    stdscr.nodelay(1)

    player_waiters = {}

    def put_player(snake, pos):
        addch(pos, BODY)
        for f in player_waiters.pop(pos, ()):
            f.set_result(snake)

    async def wait_for_player(pos):
        f = asyncio.Future()
        player_waiters.setdefault(pos, []).append(f)
        return await f

    def random_position():
        return complex(random.randint(0, width-1),
                       random.randint(0, height-1))

    class Snake:
        def __init__(self):
            self.pos = 0+0j
            self.prev_dir = self.next_dir = RIGHT
            self.steps = 0
            self.tail = [self.pos] * INITIAL_LENGTH
            self.tail_index = 0

        async def get_directions(self, it):
            async for c in it:
                if c == curses.KEY_DOWN and self.prev_dir != UP:
                    self.next_dir = 0+1j
                elif c == curses.KEY_RIGHT and self.prev_dir != LEFT:
                    self.next_dir = 1+0j
                elif c == curses.KEY_UP and self.prev_dir != DOWN:
                    self.next_dir = 0-1j
                elif c == curses.KEY_LEFT and self.prev_dir != RIGHT:
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
        move(the_snake.pos)
        stdscr.refresh()

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


    async def play(snakes):
        while True:
            for snake in snakes:
                snake.step()
            refresh()
            await asyncio.sleep(0.1)

    loop = asyncio.get_event_loop()
    tasks = [
        asyncio.ensure_future(food_loop(5+5j)),
        asyncio.ensure_future(
            the_snake.get_directions(CursesCharacters())),
        asyncio.ensure_future(play([the_snake])),
    ]
    try:
        done, not_done = loop.run_until_complete(
            asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION))
        done_values = [f.result() for f in done]
        msg = str(done_values)
    except GameOver as exn:
        msg = exn.args[0]

    raise SystemExit('\n'.join(
        [str(msg),
         "You ate %s foods" % (len(the_snake.tail) - INITIAL_LENGTH),
         "You moved %s tiles" % the_snake.steps,
         "Good job!!"]))


def wrapper(func):
    stdscr = curses.initscr()
    try:
        # Turn off echoing of keys, and enter cbreak mode,
        # where no buffering is performed on keyboard input
        curses.noecho()
        curses.cbreak()

        # In keypad mode, escape sequences for special keys
        # (like the cursor keys) will be interpreted and
        # a special value like curses.KEY_LEFT will be returned
        stdscr.keypad(1)

        # Start color, too.  Harmless if the terminal doesn't have
        # color; user can test with has_color() later on.  The try/catch
        # works around a minor bit of over-conscientiousness in the curses
        # module -- the error return from C start_color() is ignorable.
        # try:
        #     curses.start_color()
        # except:
        #     pass

        return func(stdscr)
    finally:
        # Set everything back to normal
        stdscr.keypad(0)
        curses.echo()
        curses.nocbreak()
        curses.endwin()


if __name__ == "__main__":
    wrapper(main)
