import sys
import curses
import asyncio
import functools


def complex_wrap(fn):
    @functools.wraps(fn)
    def wrapped(pos, *args):
        return fn(int(pos.imag), int(pos.real), *args)

    return wrapped


async def async_getch(stdscr):
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
    def __init__(self, stdscr):
        self.stdscr = stdscr

    async def __aiter__(self):
        return self

    async def __anext__(self):
        return await async_getch(self.stdscr)


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

        curses.start_color()

        return func(stdscr)
    finally:
        # Set everything back to normal
        stdscr.keypad(0)
        curses.echo()
        curses.nocbreak()
        curses.endwin()
