import math
import curses
import random
import asyncio

from collections import namedtuple

from asyncsnake import LockstepConsumers
from asyncsnake import run_coroutines, WaitMap
from cursessnake import CursesCharacters
from cursessnake import wrapper


class GameOver(Exception):
    pass


UP = 0-1j
RIGHT = 1+0j
DOWN = 0+1j
LEFT = -1+0j

INITIAL_LENGTH = 6


class ScreenBase:
    COLORS = None
    BLANK = ' '

    def __init__(self, stdscr):
        self.board = {}
        self.stdscr = stdscr
        self.stdscr.nodelay(1)
        curses.curs_set(0)
        self._color_id = {k: i
                          for i, k in enumerate(self.COLORS.keys(), 1)}
        for k, c in self.COLORS.items():
            curses.init_pair(self._color_id[k], c, curses.COLOR_BLACK)

    def addch(self, pos, ch):
        i = int(pos.imag)
        j = int(pos.real)
        self.board[i, j] = ch
        self._update(i // 2, j)
        assert self.gettile(pos) == ch

    def gettile(self, pos):
        i = int(pos.imag)
        j = int(pos.real)
        return self.board.get((i, j), self.BLANK)

    def delch(self, pos, ch):
        if self.gettile(pos) == ch:
            self.addch(pos, self.BLANK)

    def _update(self, row, col):
        ch1 = self.board.get((2*row, col), self.BLANK)
        ch2 = self.board.get((2*row+1, col), self.BLANK)
        if ch1 != self.BLANK and ch2 != self.BLANK:
            c = '\N{FULL BLOCK}'
        elif ch1 != self.BLANK:
            c = '\N{UPPER HALF BLOCK}'
        elif ch2 != self.BLANK:
            c = '\N{LOWER HALF BLOCK}'
        else:
            c = self.BLANK
        color = next(
            (i for ch, i in self._color_id.items() if ch in (ch1, ch2)),
            0)
        self.stdscr.addstr(row, col, c, curses.color_pair(color))

    def refresh(self):
        self.stdscr.refresh()


class Screen(ScreenBase):
    BODY = 'X'
    FOOD = 'o'
    FASTER = '+'
    SLOWER = '-'
    COLORS = {BODY: curses.COLOR_BLUE,
              FOOD: curses.COLOR_YELLOW,
              FASTER: curses.COLOR_GREEN,
              SLOWER: curses.COLOR_RED}


class Tail:
    '''
    >>> t = Tail()
    >>> tjnn
    '''
    def __init__(self):
        self.positions = []
        self.index = 0

    def move(self, pos):
        try:
            old = self.positions[self.index]
            self.positions[self.index] = pos
        except IndexError:
            if len(self.positions) == 0:
                old = None
                self.positions.append(pos)
            else:
                raise
        self.index += 1
        if self.index == len(self.positions):
            self.index = 0
        return old

    def increase_length(self, n=1):
        for _ in range(n):
            self.positions.insert(self.index, self.positions[self.index])

    def view(self):
        return TailView(self)


class TailView:
    def __init__(self, source):
        self._source = source

    def __len__(self):
        return len(self._source.positions)

    def __getitem__(self, index):
        index = (index + self._source.index) % len(self)
        return self._source.positions[index]

    def __iter__(self):
        return iter(self._source.positions[self._source.index:] +
                    self._source.positions[:self._source.index])


Snake = namedtuple('Snake', 'dir speed tail player level')


class Level:
    def __init__(self, stdscr, width=30, height=20, step=0.02):
        self.screen = Screen(stdscr)
        self.waiters = WaitMap()
        self.width, self.height = width, height
        self.step = step

        self.snakes = []
        self.tails = []

        self.worm_holes = {
            self.random_position(): self.random_position()
            for _ in range(0)}

    def get_tile(self, pos):
        return self.screen.gettile(pos)

    def is_free(self, pos):
        return self.get_tile(pos) == self.screen.BLANK

    def random_position(self):
        return complex(random.randint(0, self.width-1),
                       random.randint(0, self.height-1))

    def random_free_position(self):
        p = self.random_position()
        while not self.is_free(p):
            p = self.random_position()
        return p

    def free_rect(self, pos, w, h):
        return all(self.is_free(pos + i*1j + j)
                   for i in range(h)
                   for j in range(w))

    def random_rect(self, w, h):
        max_i = self.height - (h-1)
        max_j = self.width - (w-1)
        return complex(random.randint(0, max_j-1),
                       random.randint(0, max_i//2-1)*2)

    def random_free_rect(self, w, h):
        pos = self.random_rect(w, h)
        while not self.free_rect(pos, w, h):
            pos = self.random_rect(w, h)
        return pos

    def add_rect(self, pos, ch, w, h):
        for i in range(h):
            for j in range(w):
                self.screen.addch(pos + i + j*1j, ch)

    def del_rect(self, pos, ch, w, h):
        for i in range(h):
            for j in range(w):
                self.screen.delch(pos + i + j*1j, ch)

    async def food_loop_base(self, ch, fn, w=2, h=2):
        while True:
            try:
                pos = self.random_free_rect(w, h)
            except KeyboardInterrupt:
                await asyncio.sleep(1)
                continue
            self.add_rect(pos, ch, w, h)
            self.screen.refresh()
            x = await self.wait_for_player_rect(pos, w, h)
            self.del_rect(pos, ch, w, h)
            fn(x)

    def food_loop(self):
        return self.food_loop_base(
            Screen.FOOD, lambda idx: self.tails[idx].increase_length())

    async def wait_for_player_rect(self, pos, w, h):
        futures = [self.waiters.wait(pos + i*1j + j)
                   for i in range(h)
                   for j in range(w)]
        wait = asyncio.wait(futures, return_when=asyncio.FIRST_COMPLETED)
        dones, pending = await wait
        for f in pending:
            f.cancel()
        results = []
        for done in dones:
            results.append(await done)
        return results[0]

    def put_player(self, x, pos):
        self.screen.addch(pos, self.screen.BODY)
        self.waiters.notify(pos, x)

    def clear_player(self, pos):
        self.screen.addch(pos, self.screen.BLANK)

    def has_player(self, pos):
        return self.get_tile(pos) == self.screen.BODY

    def wrap_pos(self, pos):
        pos = self.worm_holes.get(pos, pos)
        return complex(pos.real % self.width, pos.imag % self.height)

    def move(self, pos, dir):
        return self.wrap_pos(pos + dir)

    def step_snake(self, index):
        snake = self.snakes[index]
        direction = snake.player.step(snake)
        if direction == 0:
            raise GameOver("You give up?")
        pos = self.move(snake.tail[-1], direction)
        if self.has_player(pos):
            raise GameOver('Boom! You hit yourself')
        old_pos = self.tails[index].move(pos)
        if old_pos is not None:
            self.clear_player(old_pos)
        self.put_player(index, pos)
        self.snakes[index] = Snake(
            dir=direction, level=self,
            speed=snake.speed, tail=snake.tail, player=snake.player)

    def respawn_snake(self, index, player):
        if self.tails[index]:
            for c in self.tails[index].view():
                self.clear_player(c)
        pos = self.random_free_position()
        self.tails[index] = Tail()
        self.tails[index].move(pos)
        self.tails[index].increase_length(
            getattr(player, 'initial_length', 1) - 1)
        self.snakes[index] = Snake(
            dir=1+0j, speed=5, level=self,
            tail=self.tails[index].view(), player=player)
        self.put_player(index, pos)

    async def play(self, players):
        self.snakes = [None]*len(players)
        self.tails = [None]*len(players)
        for i, p in enumerate(players):
            self.respawn_snake(i, p)
        t = 0
        n = [0] * len(self.snakes)
        while True:
            i = min(range(len(self.snakes)), key=lambda i: n[i])
            if n[i] > t:
                self.screen.refresh()
                await asyncio.sleep(self.step * (n[i] - t))
                t = n[i]
            try:
                self.step_snake(i)
            except GameOver:
                self.respawn_snake(i, self.snakes[i].player)
            w = max(1, math.ceil(math.log(len(self.tails[i].positions), 2)))
            n[i] += w


class AutoSnake:
    def __init__(self):
        self.route = []
        self.route_guard = None

    def reroute(self, state):
        level = state.level
        # if self.wait > 1:
        #     target = Screen.FASTER
        # else:
        #     target = Screen.FOOD
        target = Screen.FOOD
        res = self.route_to(level, state.tail[-1], target)
        if res:
            target_pos, self.route = res

            def guard():
                next_pos = level.move(state.tail[-1], self.route[-1])
                return (level.get_tile(next_pos) in (target, Screen.BLANK) and
                        level.get_tile(target_pos) == target)

            self.route_guard = target_pos and guard
        else:
            self.route = self.compress(level, state.tail)

            def guard():
                next_pos = level.move(state.tail[-1], self.route[-1])
                return not level.has_player(next_pos)

            self.route_guard = guard

    def compress(self, level, tail):
        p = tail[-1]
        d = 1
        res = []
        for i in range(min(10, len(tail) // 2)):
            for r in (1j, 1, -1j):
                t = level.move(p, d*r)
                if not level.has_player(t):
                    d = d * r
                    p += d
                    res.append(d)
                    break
            else:
                break
        res.reverse()
        return res or [0]

    def route_to(self, level, pos, target):
        parent = {pos: None}

        def backtrack(p):
            res = []
            while parent[p]:
                d, p = parent[p]
                res.append(d)
            return res

        n = [pos]
        i = 0
        while i < len(n):
            p = n[i]
            i += 1
            v = level.get_tile(p)
            if v == target:
                return p, backtrack(p)
            elif v != Screen.BLANK and p != pos:
                continue
            for dir in (0-1j, -1+0j, 0+1j, 1+0j):
                q = level.move(p, dir)
                if q not in parent:
                    parent[q] = (dir, p)
                    n.append(q)

    def step(self, state):
        if not self.route or (self.route_guard and not self.route_guard()):
            self.reroute(state)
        return self.route.pop()


class HumanSnake:
    initial_length = 10

    def __init__(self, controls=None):
        self.steps = 0
        if controls is None:
            controls = [curses.KEY_UP,
                        curses.KEY_LEFT,
                        curses.KEY_DOWN,
                        curses.KEY_RIGHT]
        else:
            controls = [ord(c) if isinstance(c, str)
                        else c for c in controls]
        self.controls = controls
        self.prev_dir = 0
        self.next_dir = 1+0j

    async def get_directions(self, it):
        async for c in it:
            try:
                i = self.controls.index(c)
            except ValueError:
                continue
            next_dir = [0-1j, -1+0j, 0+1j, 1+0j][i]
            if next_dir == -self.prev_dir:
                # self.next_dir = 0
                pass
            else:
                self.next_dir = next_dir

    def step(self, state):
        self.prev_dir = self.next_dir
        return self.next_dir


def main(stdscr):
    level = Level(stdscr)

    # width = 160
    # height = 90
    # width, height = 30, 20
    # width, height = 15, 15
    # width, height = 160, 90

    def faster_loop():
        return level.food_loop_base(Screen.FASTER, lambda p: p.faster())

    def slower_loop():
        return level.food_loop_base(Screen.SLOWER, lambda p: p.slower())

    input = LockstepConsumers()
    humans = [
        HumanSnake(),
    ]
    robots = [
        AutoSnake(),
        # AutoSnake(),
        # AutoSnake(),
        # AutoSnake(),
    ]
    tasks = [
        input.consume(CursesCharacters(stdscr)),
        level.food_loop(),
        # food_loop(),
        # food_loop(),
        # food_loop(),
        # food_loop(),
        # faster_loop(),
        # slower_loop(),
        level.play(humans + robots),
    ]
    for s in humans:
        tasks.append(
            s.get_directions(input.consumer()))
    try:
        msg = str(run_coroutines(tasks))
    except GameOver as exn:
        msg = exn.args[0]
    except KeyboardInterrupt:
        raise
        msg = 'Thanks for playing!'

    raise SystemExit('\n'.join(
        [str(msg),
         # "You ate %s foods" % (len(the_snake.tail) - INITIAL_LENGTH),
         # "You moved %s tiles" % the_snake.steps,
         "Good job!!"]))


if __name__ == "__main__":
    wrapper(main)
