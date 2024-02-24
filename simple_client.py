import sys
import time
import random
import logging
import contextlib

import asyncio
from asyncio import Queue
import aiohttp
import async_timeout

# Multi-threading uses threads and is managed by the operating system's scheduler, while coroutines use the asyncio library and are managed by the asyncio event loop. Both mechanisms allow you to write code that can handle multiple I/O operations concurrently, but they do not provide true parallelism due to the GIL.
# region: DO NOT CHANGE - the code within this region can be assumed to be "correct"

PER_SEC_RATE = 20
DURATION_MS_BETWEEN_REQUESTS = int(1000 / PER_SEC_RATE)
REQUEST_TTL_MS = 1000
VALID_API_KEYS = ['UT4NHL1J796WCHULA1750MXYF9F5JYA6',
                  '8TY2F3KIL38T741G1UCBMCAQ75XU9F5O',
                  '954IXKJN28CBDKHSKHURQIVLQHZIEEM9',
                  'EUU46ID478HOO7GOXFASKPOZ9P91XGYS',
                  '46V5EZ5K2DFAGW85J18L50SGO25WJ5JE']


async def generate_requests(queue: Queue):
    """
    co-routine responsible for generating requests

    :param queue:
    :param logger:
    :return:
    """
    curr_req_id = 0
    # 1000 / PER_SEC_RATE / len(VALID_API_KEYS) -> DURATION_BTW_REQUEST_WITH_MULTIPLE_KEYS
    MAX_SLEEP_MS = 1000 / PER_SEC_RATE / len(VALID_API_KEYS) * 1.05 * 2.0
    while True:
        queue.put_nowait(Request(curr_req_id))
        curr_req_id += 1
        sleep_ms = random.randint(0, MAX_SLEEP_MS)
        await asyncio.sleep(sleep_ms / 1000.0)


def timestamp_ms() -> int:
    return int(time.time() * 1000)

# endregion


def configure_logger(name=None):
    logger = logging.getLogger(name)
    if name is None:
        # only add handlers to root logger
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(formatter)
        logger.addHandler(sh)

        fh = logging.FileHandler(f"async-debug.log", mode="a")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        logger.setLevel(logging.DEBUG)
    return logger


class RateLimiterTimeout(Exception):
    pass


class RateLimiter:
    def __init__(self, per_second_rate, min_duration_ms_between_requests):
        self.__per_second_rate = per_second_rate
        self.__min_duration_ms_between_requests = min_duration_ms_between_requests
        self.__last_request_time = 0
        self.__request_times = [0] * per_second_rate
        self.__curr_idx = 0

    # asynchronous context managers. Context managers are objects that define a __enter__ and __exit__ method,
    # and they are typically used with the with statement to manage resources that need to be acquired and released in a safe and predictable manner.
    @contextlib.asynccontextmanager
    async def acquire(self, timeout_ms=0):
        # more time before timeout
        timeout_ms += 25
        enter_ms = timestamp_ms()
        while True:
            # larger offset -> more likely to timeout
            # more "time" between requests -> higher rate
            now = timestamp_ms() + 25

            # TODO: Outdated request while trying to acquire
            if now - enter_ms > timeout_ms > 0:
                raise RateLimiterTimeout()

            # ensure min duration between sequential requests
            if now - self.__last_request_time <= self.__min_duration_ms_between_requests:
                await asyncio.sleep(0.0005)
                continue
            
            # ensure adherence to per_sec_rate limit
            if now - self.__request_times[self.__curr_idx] <= 1000:
                await asyncio.sleep(0.0005)
                continue

            break
        
        # Adherence to rate limits have been ensured

        # set last request time to current time, and also store in request_times array
        self.__last_request_time = self.__request_times[self.__curr_idx] = now - 25
        # index to use to reference request_times array
        self.__curr_idx = (self.__curr_idx + 1) % self.__per_second_rate
        yield self


async def exchange_facing_worker(url: str, api_key: str, queue: Queue, logger: logging.Logger, throughput: list[int]):
    rate_limiter = RateLimiter(PER_SEC_RATE, DURATION_MS_BETWEEN_REQUESTS)
    async with aiohttp.ClientSession() as session:
        while True:
            # get request from queue
            request: Request = await queue.get()
            
            # extra time to offset low throughput due to overhead
            # Max: 100 request / s -> 
            # extra_time = throughput[1]/100
            # time since request creation
            remaining_ttl = REQUEST_TTL_MS - (timestamp_ms() - request.create_time) + 100

            # TODO: Outdated request before trying to acquire -> 
            if remaining_ttl <= 0:
                logger.warning(f"ignoring request {request.req_id} from queue due to TTL")
                continue

            try:
                nonce = timestamp_ms()
                # rate limiter ensures adherence to per second rate limits and expiry of requests when waiting
                async with rate_limiter.acquire(timeout_ms=remaining_ttl):
                    # ensure api call does not take more than 1 sec
                    async with async_timeout.timeout(1.0):
                        data = {'api_key': api_key, 'nonce': nonce, 'req_id': request.req_id}
                        async with session.request('GET',
                                                   url,
                                                   data=data) as resp:  # type: aiohttp.ClientResponse
                            # return control to the event loop to continue running other tasks while waiting for the response to arrive
                            json = await resp.json()
                            throughput[0] += 1
                            if json['status'] == 'OK':
                                logger.info(f"API response: status {resp.status}, resp {json}")
                            else:
                                logger.warning(f"API response: status {resp.status}, resp {json}")
            except RateLimiterTimeout:
                logger.warning(f"ignoring request {request.req_id} in limiter due to TTL")


class Request:
    def __init__(self, req_id):
        self.req_id = req_id
        self.create_time = timestamp_ms()

async def log_throughput(throughput: list[int], logger: logging.Logger):
    while True:
        await asyncio.sleep(1)
        logger.info(f"Throughput: {throughput[0]} requests made / second")
        throughput[1] = throughput[0]
        throughput[0] = 0

def main():
    url = "http://127.0.0.1:9999/api/request"
    loop = asyncio.get_event_loop()
    queue = Queue()
    throughput = [0, 0]

    logger = configure_logger()
    loop.create_task(generate_requests(queue=queue))

    for api_key in VALID_API_KEYS:
        loop.create_task(exchange_facing_worker(url=url, api_key=api_key, queue=queue, logger=logger, throughput=throughput))
    
    loop.create_task(log_throughput(throughput=throughput, logger=logger))

    loop.run_forever()

if __name__ == '__main__':
    main()
