import asyncio


class LockstepConsumer:
    def __init__(self, f):
        self.f = f

    async def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.f()


class LockstepConsumers:
    def __init__(self):
        self.consumers = 0
        self.futures = []
        self._waiter = None

    async def consume(self, it):
        async for v in it:
            await self.push(v)

    def consumer(self):
        self.consumers += 1
        return LockstepConsumer(self._consume_next)

    async def _consume_next(self):
        f = asyncio.Future()
        self.futures.append(f)
        self._notify()
        return await f

    def _notify(self):
        if self._waiter:
            self._waiter.set_result(None)
            self._waiter = None

    async def _wait(self):
        f = asyncio.Future()
        self._waiter = f
        await self._waiter

    async def push(self, v):
        while len(self.futures) < self.consumers:
            await self._wait()
        for f in self.futures:
            f.set_result(v)
        self.futures = []
