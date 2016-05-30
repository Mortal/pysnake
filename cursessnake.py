import sys
import asyncio


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
