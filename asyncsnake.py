import asyncio


class LockstepConsumer:
    def __init__(self, f):
        self.f = f

    async def __aiter__(self):
        return self

    def __anext__(self):
        return self.f()


class LockstepConsumers:
    def __init__(self):
        self.consumers = 0
        self.futures = []
        self._waiter = None

    async def consume(self, it):
        async for v in it:
            await self.push(v)
        await self.stop()

    def consumer(self):
        self.consumers += 1
        return LockstepConsumer(self._consume_next)

    def _consume_next(self):
        f = asyncio.Future()
        self.futures.append(f)
        self._notify()
        return f

    def _notify(self):
        if self._waiter:
            self._waiter.set_result(None)
            self._waiter = None

    def _wait(self):
        f = asyncio.Future()
        self._waiter = f
        return self._waiter

    async def push(self, v):
        while len(self.futures) < self.consumers:
            await self._wait()
        for f in self.futures:
            f.set_result(v)
        self.futures = []

    async def stop(self):
        while len(self.futures) < self.consumers:
            await self._wait()
        for f in self.futures:
            f.set_exception(StopAsyncIteration())
        self.futures = []
        self.stopped = True


def run_coroutines(tasks):
    "Helper function that runs some coroutines and cleans up after exceptions."
    loop = asyncio.get_event_loop()
    tasks = [asyncio.ensure_future(t, loop=loop) for t in tasks]

    # Run coroutines until the first raises an exception.
    tasks_wait = asyncio.ensure_future(
        asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION),
        loop=loop)
    try:
        done, pending = loop.run_until_complete(tasks_wait)
    except:
        tasks_wait.cancel()
        loop.run_forever()
        for p in tasks:
            p.cancel()
        for p in tasks:
            try:
                loop.run_until_complete(p)
            except asyncio.CancelledError:
                pass
        loop.close()
        raise
    else:
        # Cancel coroutines that are not done.
        for p in pending:
            p.cancel()
        # Wait for cancellations.
        for p in pending:
            try:
                loop.run_until_complete(p)
            except asyncio.CancelledError:
                pass
        try:
            # Handle the original exception or let it bubble up.
            return [f.result() for f in done]
        finally:
            loop.close()
