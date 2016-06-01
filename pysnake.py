import sys
import curses
import random
import asyncio

from asyncsnake import LockstepConsumers
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


def main(stdscr):
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

    def wait_for_player(pos):
        f = asyncio.Future()
        player_waiters.setdefault(pos, []).append(f)
        return f

    def random_position():
        return complex(random.randint(0, width-1),
                       random.randint(0, height-1))

    class Snake:
        def __init__(self, pos=None, dir=None, controls=None):
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

    input = LockstepConsumers()
    loop = asyncio.get_event_loop()
    snakes = [the_snake, Snake(pos=0+10j, controls='wasd')]
    tasks = [
        input.consume(CursesCharacters(stdscr)),
        food_loop(5+5j),
        play(snakes),
    ]
    for s in snakes:
        tasks.append(
            s.get_directions(input.consumer()))
    tasks = [asyncio.ensure_future(t, loop=loop) for t in tasks]

    # Run coroutines until the first raises an exception.
    tasks_wait = asyncio.ensure_future(
        asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION),
        loop=loop)
    try:
        done, pending = loop.run_until_complete(tasks_wait)
    except:
        # Exception was raised in run_until_complete, but not in any future --
        # add dummy future with current exception.
        tasks_wait.cancel()
        pending = tasks
        done = [asyncio.Future()]
        done[0].set_exception(sys.exc_info()[1])

    # Cancel coroutines that are not done.
    for p in pending:
        p.cancel()
    # Wait for cancellations.
    loop.stop()
    loop.run_forever()
    try:
        # Handle the original exception or let it bubble up.
        for f in done:
            f.result()
    except GameOver as exn:
        msg = exn.args[0]
    except KeyboardInterrupt:
        msg = 'You killed the game!'
    else:
        msg = str(done)
    loop.close()

    raise SystemExit('\n'.join(
        [str(msg),
         "You ate %s foods" % (len(the_snake.tail) - INITIAL_LENGTH),
         "You moved %s tiles" % the_snake.steps,
         "Good job!!"]))


if __name__ == "__main__":
    wrapper(main)
