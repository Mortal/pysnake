import sys
import curses
import random
import asyncio
import functools


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

    def put_player(pos):
        addch(pos, BODY)
        for f in player_waiters.pop(pos, ()):
            f.set_result(None)

    async def wait_for_player(pos):
        f = asyncio.Future()
        player_waiters.setdefault(pos, []).append(f)
        await f

    def random_position():
        return complex(random.randint(0, width-1),
                       random.randint(0, height-1))

    pos = 0+0j
    prev_dir = RIGHT
    next_dir = RIGHT

    def refresh():
        move(pos)
        stdscr.refresh()

    async def get_directions(it):
        nonlocal prev_dir, next_dir
        async for c in it:
            if c == curses.KEY_DOWN and prev_dir != UP:
                next_dir = 0+1j
            elif c == curses.KEY_RIGHT and prev_dir != LEFT:
                next_dir = 1+0j
            elif c == curses.KEY_UP and prev_dir != DOWN:
                next_dir = 0-1j
            elif c == curses.KEY_LEFT and prev_dir != RIGHT:
                next_dir = -1+0j

    width = 30
    height = 20
    snake = [pos] * INITIAL_LENGTH

    async def food_loop(pos):
        while True:
            while gettile(pos) != ' ':
                pos = random_position()
            addch(pos, FOOD)
            refresh()
            await wait_for_player(pos)
            snake[:] = snake[:i] + [snake[i]] + snake[i:]
            pos = random_position()

    asyncio.ensure_future(food_loop(5+5j))

    i = 0
    steps = 0

    async def play():
        nonlocal steps, i, next_dir, prev_dir, pos
        while True:
            addch(snake[i], ' ')
            pos += next_dir
            pos = complex(pos.real % width, pos.imag % height)
            prev_dir = next_dir
            cur_tile = gettile(pos)
            if cur_tile == BODY:
                return "Boom! You hit yourself"
            snake[i] = pos
            put_player(pos)
            refresh()
            i += 1
            steps += 1
            if i == len(snake):
                i = 0
            await asyncio.sleep(0.1)

    loop = asyncio.get_event_loop()
    asyncio.ensure_future(get_directions(CursesCharacters()))
    msg = loop.run_until_complete(play())

    raise SystemExit('\n'.join(
        [msg,
         "You ate %s foods" % (len(snake) - INITIAL_LENGTH),
         "You moved %s tiles" % steps,
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
