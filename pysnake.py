import curses
import random
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
    addch = complex_wrap(stdscr.addch)
    move = complex_wrap(stdscr.move)
    inch = complex_wrap(stdscr.inch)

    def gettile(pos):
        return chr(inch(pos) & 0xFF)

    stdscr.nodelay(1)

    pos = 0+0j
    prev_dir = RIGHT
    next_dir = RIGHT

    width = 30
    height = 20
    snake = [pos] * INITIAL_LENGTH

    addch(5+5j, FOOD)

    msg = None

    i = 0
    steps = 0
    while True:
        addch(snake[i], ' ')
        while True:
            c = stdscr.getch()
            if c == -1:
                break
            if c == curses.KEY_DOWN and prev_dir != UP:
                next_dir = 0+1j
            elif c == curses.KEY_RIGHT and prev_dir != LEFT:
                next_dir = 1+0j
            elif c == curses.KEY_UP and prev_dir != DOWN:
                next_dir = 0-1j
            elif c == curses.KEY_LEFT and prev_dir != RIGHT:
                next_dir = -1+0j
        pos += next_dir
        prev_dir = next_dir
        pos = complex(pos.real % width, pos.imag % height)
        cur_tile = gettile(pos)
        add_new = False
        if cur_tile == FOOD:
            snake = snake[:i] + [snake[i]] + snake[i:]
            add_new = True
        elif cur_tile != ' ':
            msg = (
                "Boom! You hit %s" %
                'yourself' if cur_tile == BODY else repr(cur_tile))
            break
        snake[i] = pos
        addch(pos, BODY)

        if add_new:
            o_pos = pos
            while gettile(o_pos) != ' ':
                o_pos = complex(random.randint(0, width-1),
                                random.randint(0, height-1))
            addch(o_pos, FOOD)
        move(pos)
        stdscr.refresh()
        curses.napms(100)

        i += 1
        steps += 1
        if i == len(snake):
            i = 0

    raise SystemExit('\n'.join(
        [msg,
         "You ate %s foods" % (len(snake) - INITIAL_LENGTH),
         "You moved %s tiles" % steps,
         "Good job!!",
        ]))


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
