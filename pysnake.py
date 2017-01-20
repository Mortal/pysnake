import math
import curses
import random
import asyncio

from asyncsnake import LockstepConsumers, run_coroutines, WaitMap
from cursessnake import CursesCharacters, wrapper


class GameOver(Exception):
    pass


UP = 0-1j
RIGHT = 1+0j
DOWN = 0+1j
LEFT = -1+0j

INITIAL_LENGTH = 6


class ScreenBase:
    COLORS = None

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
        return self.board.get((i, j), ' ')

    def delch(self, pos, ch):
        if self.gettile(pos) == ch:
            self.addch(pos, ' ')

    def _update(self, row, col):
        ch1 = self.board.get((2*row, col), ' ')
        ch2 = self.board.get((2*row+1, col), ' ')
        if ch1 != ' ' and ch2 != ' ':
            c = '\N{FULL BLOCK}'
        elif ch1 != ' ':
            c = '\N{UPPER HALF BLOCK}'
        elif ch2 != ' ':
            c = '\N{LOWER HALF BLOCK}'
        else:
            c = ' '
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


def main(stdscr):
    screen = Screen(stdscr)

    player_waiters = WaitMap()

    def put_player(snake, pos):
        screen.addch(pos, screen.BODY)
        player_waiters.notify(pos, snake)

    async def wait_for_player_rect(pos, w, h):
        futures = [player_waiters.wait(pos + i*1j + j)
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

    def random_position():
        return complex(random.randint(0, width-1),
                       random.randint(0, height-1))

    def random_rect(w, h):
        max_i = height - (h-1)
        max_j = width - (w-1)
        return complex(random.randint(0, max_j-1),
                       random.randint(0, max_i//2-1)*2)

    class Snake:
        def __init__(self, pos=None, dir=None, controls=None, speed=None, length=None):
            self.wait = speed or 10
            if pos is None:
                self.pos = 0+0j
            else:
                self.pos = pos
            if dir is None:
                self.prev_dir = self.next_dir = RIGHT
            else:
                self.prev_dir = self.next_dir = dir
            self.steps = 0
            self.tail = [self.pos] * (length or INITIAL_LENGTH)
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
                try:
                    i = self.controls.index(c)
                except ValueError:
                    continue
                next_dir = [0-1j, -1+0j, 0+1j, 1+0j][i]
                if next_dir == -self.prev_dir:
                    self.next_dir = 0
                else:
                    self.next_dir = next_dir

        def wrap_pos(self, pos):
            pos = WORM.get(pos, pos)
            return complex(pos.real % width, pos.imag % height)

        def step(self):
            if self.next_dir == 0:
                return
            screen.addch(self.tail[self.tail_index], ' ')
            self.pos = self.wrap_pos(self.pos + self.next_dir)
            self.prev_dir = self.next_dir
            cur_tile = screen.gettile(self.pos)
            if cur_tile == screen.BODY:
                raise GameOver("Boom! You hit yourself")
            self.tail[self.tail_index] = self.pos
            put_player(self, self.pos)
            self.tail_index += 1
            self.steps += 1
            if self.tail_index == len(self.tail):
                self.tail_index = 0

        def slower(self):
            self.wait = self.wait + 1

        def faster(self):
            self.wait = max(1, self.wait - 1)

        def on_eat_food(self):
            self.tail.insert(self.tail_index, self.tail[self.tail_index])
            if len(self.tail) == width * height:
                raise GameOver("You win!")

    class AutoSnake(Snake):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.route = []
            self.route_guard = None

        async def get_directions(self, it):
            async for c in it:
                pass

        def route_next(self):
            if not self.route:
                return
            if self.route_guard and not self.route_guard():
                return
            next_pos = self.wrap_pos(self.pos + self.route[-1])
            # if screen.gettile(next_pos) == screen.BODY:
            #     return
            self.next_dir = self.route.pop()
            return True

        def reroute(self):
            # if self.wait > 1:
            #     target = screen.FASTER
            # else:
            #     target = screen.FOOD
            target = screen.FOOD
            res = self.route_to(target)
            if res:
                target_pos, self.route = res

                def guard():
                    next_pos = self.wrap_pos(self.pos + self.route[-1])
                    return (screen.gettile(next_pos) in (target, ' ') and
                            screen.gettile(target_pos) == target)

                self.route_guard = target_pos and guard
            else:
                self.route = self.compress()

                def guard():
                    next_pos = self.wrap_pos(self.pos + self.route[-1])
                    return screen.gettile(next_pos) != screen.BODY

                self.route_guard = guard

        def compress(self):
            p = self.pos
            d = self.prev_dir
            res = []
            for i in range(min(10, len(self.tail) // 2)):
                for r in (1j, 1, -1j):
                    t = self.wrap_pos(p + d*r)
                    if screen.gettile(t) != screen.BODY:
                        d = d * r
                        p += d
                        res.append(d)
                        break
                else:
                    break
            res.reverse()
            return res or [0]

        def route_to(self, target):
            parent = {self.pos: None}

            def backtrack(p):
                res = []
                while parent[p]:
                    d, p = parent[p]
                    res.append(d)
                return res

            n = [self.pos]
            i = 0
            while i < len(n):
                p = n[i]
                i += 1
                v = screen.gettile(p)
                if v == target:
                    return p, backtrack(p)
                elif v != ' ' and p != self.pos:
                    continue
                for dir in (0-1j, -1+0j, 0+1j, 1+0j):
                    q = self.wrap_pos(p + dir)
                    if q not in parent:
                        parent[q] = (dir, p)
                        n.append(q)

        def step(self):
            if not self.route_next():
                self.reroute()
                self.route_next()
            super().step()

    # width = 160
    # height = 90
    width, height = 30, 20
    # width, height = 15, 15
    # width, height = 160, 90

    WORM = {random_position(): random_position()
            for _ in range(3)}

    def free_rect(pos, w, h):
        return all(screen.gettile(pos + i*1j + j) == ' '
                   for i in range(h)
                   for j in range(w))

    def add_rect(pos, ch, w, h):
        for i in range(h):
            for j in range(w):
                screen.addch(pos + i + j*1j, ch)

    def del_rect(pos, ch, w, h):
        for i in range(h):
            for j in range(w):
                screen.delch(pos + i + j*1j, ch)

    async def food_loop_base(ch, fn):
        pos = random_rect(2, 2)
        while True:
            while not free_rect(pos, 2, 2):
                pos = random_rect(2, 2)
            add_rect(pos, ch, 2, 2)
            screen.refresh()
            p = await wait_for_player_rect(pos, 2, 2)
            del_rect(pos, ch, 2, 2)
            fn(p)
            pos = random_rect(2, 2)

    def food_loop():
        return food_loop_base(screen.FOOD, lambda p: p.on_eat_food())

    def faster_loop():
        return food_loop_base(screen.FASTER, lambda p: p.faster())

    def slower_loop():
        return food_loop_base(screen.SLOWER, lambda p: p.slower())

    async def play(snakes):
        t = 0
        n = [0] * len(snakes)
        while True:
            i = min(range(len(snakes)), key=lambda i: n[i])
            if n[i] > t:
                screen.refresh()
                await asyncio.sleep(0.01 * (n[i] - t))
                t = n[i]
            try:
                snakes[i].step()
            except GameOver:
                for c in snakes[i].tail:
                    screen.addch(c, ' ')
                s = max(1, snakes[i].wait-1)
                del snakes[i]
                pos = random_position()
                while screen.gettile(pos) != ' ':
                    pos = random_position()
                snakes.append(AutoSnake(speed=s, pos=pos, length=1))
                continue
            w = max(1, math.ceil(math.log(len(snakes[i].tail), 2)))
            n[i] += w

    # input = LockstepConsumers()
    snakes = [
              AutoSnake(speed=4, pos=0+10j),
              AutoSnake(speed=4, pos=10+12j),
              # AutoSnake(speed=4, pos=15+12j),
              # AutoSnake(speed=4, pos=0+16j),
             ]
    tasks = [
        # input.consume(CursesCharacters(stdscr)),
        food_loop(),
        # food_loop(),
        # food_loop(),
        # food_loop(),
        # food_loop(),
        # faster_loop(),
        # slower_loop(),
        play(snakes),
    ]
    # for s in snakes:
    #     tasks.append(
    #         s.get_directions(input.consumer()))
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
