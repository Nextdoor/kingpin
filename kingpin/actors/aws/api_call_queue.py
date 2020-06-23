from boto import exception as boto_exception
from botocore import exceptions as botocore_exceptions
from tornado import concurrent
from tornado import gen
from tornado import queues
from tornado import ioloop

EXECUTOR = concurrent.futures.ThreadPoolExecutor(10)


class ApiCallQueue:
    """
    Handles queueing up and sending AWS api calls serially,
    with exponential backoff when there is throttling.

    Supports both boto2 and boto3.

    Invoke the `call` method to queue up a new API call.
    """

    def __init__(self):
        self.executor = EXECUTOR

        self._queue = queues.Queue()
        ioloop.IOLoop.current().spawn_callback(self._process_queue)

        # Used for controlling how fast the work queue is processed,
        # with exponential delay on throttling errors.
        self.delay_min = 0.25
        self.delay_max = 30
        # We don't have a delay until we first get throttled.
        self.delay = 0

        # There are a number of different rate limiting messages
        # boto2 can return when rate limits are reached, depending
        # on which apis are used.
        self.boto2_throttle_strings = (
            'Throttling',
            'Rate exceeded',
            'reached max retries',
        )

    @gen.coroutine
    def call(self, api_function, *args, **kwargs):
        """Call a boto2 or boto3 api function.

        Simply invoke this with an api method and its args and kwargs.

        The api function call is coordinated synchronously across all
        calls to this `api_call_queue`, and they will run in order.

        I.e., if you invoke this right after another coroutine invoked this,
        it will block until that other coroutine's call completed.

        If the call ends up being rate limited,
        it will backoff and try again continuously.

        By serializing the api calls to the specific method,
        this prevents a stampeding herd effect that you'd normally get
        with infinite retries.

        There is no limit or timeout on how many times it will retry,
        so in practice this may block an extremely long time if all responses
        are rate limit exceptions.

        Any other failures, like connection timeouts or read timeouts,
        will bubble up immediately and won't be retried here.
        """
        result_queue = queues.Queue(maxsize=1)
        yield self._queue.put((result_queue, api_function, args, kwargs))
        result = yield result_queue.get()
        if isinstance(result, Exception):
            raise result
        raise gen.Return(result)

    @gen.coroutine
    def _process_queue(self):
        """Queue consumer.

        Reads the api functions to call from the internal queue
        along with their individual result queues.
        Calls the api function.
        That result queue is used to pass back the result
        or exception from the call.
        This sleeps between API calls based on `delay`.
        """
        while True:
            result_queue, api_function, args, kwargs = yield self._queue.get()
            try:
                result = yield self._call(api_function, *args, **kwargs)
            except Exception as e:
                result = e
            yield result_queue.put(result)
            yield gen.sleep(self.delay)

    @gen.coroutine
    def _call(self, api_function, *args, **kwargs):
        """Calls the provided api_function in a background thread.

        If the api function returns a response cleanly, this will return it.
        If the api function raises an exception, this raises it up.

        For as long as the api function returns a boto2 or boto3
        rate limiting exception, this will backoff and try again.
        """
        while True:
            try:
                result = yield self._thread(api_function, *args, **kwargs)
                self._decrease_delay()
                raise gen.Return(result)
            except boto_exception.BotoServerError as e:
                # Boto2 exception.
                if e.error_code in self.boto2_throttle_strings:
                    self._increase_delay()
                    yield gen.sleep(self.delay)
                else:
                    self._decrease_delay()
                    raise e
            except botocore_exceptions.ClientError as e:
                # Boto3 exception.
                if e.response['Error']['Code'] == 'Throttling':
                    self._increase_delay()
                    yield gen.sleep(self.delay)
                else:
                    self._decrease_delay()
                    raise e

    def _decrease_delay(self):
        """Decrease `delay` by one step.

        If `delay` is already 0, do nothing.
        If `delay` is `delay_min`, go to 0.

        Otherwise, divide `delay` by 2.
        If that goes below `delay_min`, go to `delay_min`.
        """
        if self.delay == 0:
            return
        if self.delay == self.delay_min:
            self.delay = 0
            return
        self.delay /= 2
        self.delay = max(self.delay, self.delay_min)

    def _increase_delay(self):
        """Increase `delay` by one step.

        If `delay` is already 0, go to `delay_min`.

        Otherwise, multiply `delay` by 2.
        If that goes above `delay_max`, go to `delay_max`.
        """
        if self.delay == 0:
            self.delay = self.delay_min
            return
        self.delay *= 2
        self.delay = min(self.delay, self.delay_max)

    @concurrent.run_on_executor
    def _thread(self, function, *args, **kwargs):
        """Execute `function` in a concurrent thread.

        This allows execution of any function in a thread without having
        to write a wrapper method that is decorated with run_on_executor().
        """
        return function(*args, **kwargs)
