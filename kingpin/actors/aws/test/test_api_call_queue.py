import logging
import time

from boto import exception as boto_exception
from botocore import exceptions as botocore_exceptions
from tornado import concurrent
from tornado import gen
from tornado import testing

from kingpin.actors.aws import api_call_queue

log = logging.getLogger(__name__)


class TestApiCallQueue(testing.AsyncTestCase):
    boto2_exception = boto_exception.BotoServerError(
        '400', 'Bad request',
        {'Error': {'Code': 'Bad request'}})
    boto2_throttle_exception_1 = boto_exception.BotoServerError(
        '429', 'Rate limit',
        {'Error': {'Code': 'Throttling'}})
    boto2_throttle_exception_2 = boto_exception.BotoServerError(
        '429', 'Rate limit',
        {'Error': {'Code': 'Rate exceeded'}})
    boto2_throttle_exception_3 = boto_exception.BotoServerError(
        '429', 'Rate limit',
        {'Error': {'Code': 'reached max retries'}})

    boto3_exception = botocore_exceptions.ClientError(
        {'Error': {'Code': 'Bad request'}}, 'Test')
    boto3_throttle_exception = botocore_exceptions.ClientError(
        {'Error': {'Code': 'Throttling'}}, 'Test')

    def setUp(self):
        super(TestApiCallQueue, self).setUp()
        self.api_call_queue = api_call_queue.ApiCallQueue()
        self.api_call_queue.delay_min = 0.05
        self.api_call_queue.delay_max = 0.2

        self.executor = concurrent.futures.ThreadPoolExecutor(10)

    @testing.gen_test
    def test_plain_call(self):
        """Test that a single api call through the queue works."""
        result = yield self.api_call_queue.call(self._mock_api_function_sync)
        self.assertEqual(result, 'OK')

    @testing.gen_test
    def test_concurrent_calls_with_delay(self):
        """
        Test concurrent calls with some latency run serially
        and return independent results.

        The api_call_queue runs calls synchronously and serially.
        """
        api_call_queue_calls = [
            self.api_call_queue.call(
                self._mock_api_function_sync, result=1, delay=0.05),
            self.api_call_queue.call(
                self._mock_api_function_sync, result=2, delay=0.05),
            self.api_call_queue.call(
                self._mock_api_function_sync, result=3, delay=0.05),
            self.api_call_queue.call(
                self._mock_api_function_sync, result=4, delay=0.05),
            self.api_call_queue.call(
                self._mock_api_function_sync, result=5, delay=0.05),
        ]

        start = time.time()
        results = yield gen.multi(api_call_queue_calls)
        stop = time.time()
        run_time = stop - start

        self.assertTrue(0.25 <= run_time < 0.35)
        self.assertEqual(results, [1, 2, 3, 4, 5])

    @testing.gen_test
    def test_api_call_queue_future_is_nonblocking(self):
        """
        Test that the api call queue future is nonblocking for other futures.
        It needs to execute in a different thread because of the synchronous
        nature of AWS APIs.
        """
        futures = [
            self.api_call_queue.call(
                self._mock_api_function_sync, result=1, delay=0.05),
            self._mock_api_function_async(result=2, delay=0.05),
            self._mock_api_function_async(result=3, delay=0.05),
            self._mock_api_function_async(result=4, delay=0.05),
            self._mock_api_function_async(result=5, delay=0.05),
        ]

        start = time.time()
        results = yield gen.multi(futures)
        stop = time.time()
        run_time = stop - start

        self.assertTrue(0.05 <= run_time < 0.15)
        self.assertEqual(results, [1, 2, 3, 4, 5])

    @testing.gen_test
    def test_api_call_queue_raises_exceptions(self):
        """
        Test that the api call queue raises exceptions and proceeds to execute
        other queued api calls.
        """

        @gen.coroutine
        def _call_without_exception():
            result = yield self.api_call_queue.call(
                self._mock_api_function_sync, delay=0.05)
            self.assertEqual(result, 'OK')
            raise gen.Return('no exception')

        @gen.coroutine
        def _call_with_exception():
            err = ValueError('test exception')
            try:
                yield self.api_call_queue.call(
                    self._mock_api_function_sync,
                    exception=err,
                    delay=0.05)
            except Exception as e:
                self.assertEqual(err, e)
            raise gen.Return('exception')

        @gen.coroutine
        def _call_with_exception_after_boto2_rate_limit():
            """
            First rate limit, then raise an exception.
            This should take:
                call delay * 2 + min rate limiting delay * 1
            """
            try:
                yield self.api_call_queue.call(
                    self._mock_api_function_sync,
                    exception=[
                        self.boto2_throttle_exception_1,
                        self.boto2_exception],
                    delay=0.05)
            except Exception as e:
                self.assertEqual(self.boto2_exception, e)

            raise gen.Return('exception')

        @gen.coroutine
        def _call_with_exception_after_boto3_rate_limit():
            """
            First rate limit, then raise an exception.
            This should take:
                call delay * 2 + min rate limiting delay * 1
            """
            try:
                yield self.api_call_queue.call(
                    self._mock_api_function_sync,
                    exception=[
                        self.boto3_throttle_exception,
                        self.boto3_exception],
                    delay=0.05)
            except Exception as e:
                self.assertEqual(self.boto3_exception, e)

            raise gen.Return('exception')

        call_wrappers = [
            # Should take 0.05s.
            _call_without_exception(),
            # Should take 0.05s.
            _call_with_exception(),
            # Should take 0.05s.
            _call_without_exception(),
            # Should take 0.05s + 0.05s + 0.05s.
            _call_with_exception_after_boto2_rate_limit(),
            # Should take 0.05s + 0.05s + 0.05s.
            _call_with_exception_after_boto3_rate_limit(),
        ]

        start = time.time()
        results = yield gen.multi_future(call_wrappers)
        stop = time.time()
        run_time = stop - start

        self.assertTrue(0.45 <= run_time < 0.55)
        self.assertEqual(
            results,
            ['no exception', 'exception', 'no exception',
             'exception', 'exception'])

    @testing.gen_test
    def test_rate_limiting_boto2(self):
        """
        Test that rate limiting with boto2 works.
        """
        # Each one of these will raise a throttling exception, then succeed.
        # Between calls, each should delay for 1 cycle of `delay_min`.
        # Delay min is 0.05s, so total runtime should be ~0.15s.
        api_call_queue_calls = [
            self.api_call_queue.call(
                self._mock_api_function_sync,
                result=1,
                exception=[self.boto2_throttle_exception_1]),
            self.api_call_queue.call(
                self._mock_api_function_sync,
                result=2,
                exception=[self.boto2_throttle_exception_2]),
            self.api_call_queue.call(
                self._mock_api_function_sync,
                result=3,
                exception=[self.boto2_throttle_exception_3]),
        ]

        start = time.time()
        results = yield gen.multi(api_call_queue_calls)
        stop = time.time()
        run_time = stop - start

        self.assertTrue(0.15 <= run_time < 0.25)
        self.assertEqual(results, [1, 2, 3])

    @testing.gen_test
    def test_rate_limiting_boto3(self):
        """
        Test that rate limiting with boto3 works.
        """
        # Each one of these will raise a throttling exception, then succeed.
        # Between calls, each should delay for 1 cycle of `delay_min`.
        # Delay min is 0.05s, so total runtime should be ~0.15s.
        api_call_queue_calls = [
            self.api_call_queue.call(
                self._mock_api_function_sync,
                result=1,
                exception=[self.boto3_throttle_exception]),
            self.api_call_queue.call(
                self._mock_api_function_sync,
                result=2,
                exception=[self.boto3_throttle_exception]),
            self.api_call_queue.call(
                self._mock_api_function_sync,
                result=3,
                exception=[self.boto3_throttle_exception]),
        ]

        start = time.time()
        results = yield gen.multi(api_call_queue_calls)
        stop = time.time()
        run_time = stop - start

        self.assertTrue(0.15 <= run_time < 0.25)
        self.assertEqual(results, [1, 2, 3])

    @testing.gen_test
    def test_rate_limit_stepping(self):
        """
        Test that rate limiting steps delay up and down.
        """

        # The delay will step from delay_min to delay_max by doubling.
        # 0s -> 0.05s -> 0.10s -> 0.20s.
        # When a call succeeds, the delay goes back down a step.

        def _throttle_twice(result):
            # This will raise two throttling exception, then succeed.
            # Because of that, this should end with the delay going up
            # one step.
            return self.api_call_queue.call(
                self._mock_api_function_sync,
                result=result,
                exception=[
                    self.boto2_throttle_exception_1,
                    self.boto3_throttle_exception])

        api_call_queue_calls = [
            _throttle_twice(result=1),
        ]

        start = time.time()
        results = yield gen.multi(api_call_queue_calls)
        stop = time.time()
        run_time = stop - start

        # Delay should be up one step total: delay_min.

        self.assertEqual(
            self.api_call_queue.delay,
            self.api_call_queue.delay_min)
        self.assertTrue(0.15 <= run_time < 0.25)
        self.assertEqual(results, [1])

        # Do it again, to go up one more step.

        api_call_queue_calls = [
            _throttle_twice(result=2),
        ]

        start = time.time()
        results = yield gen.multi(api_call_queue_calls)
        stop = time.time()
        run_time = stop - start

        # Delay should be up two steps total: delay_min * 2.

        self.assertEqual(
            self.api_call_queue.delay,
            self.api_call_queue.delay_min * 2)
        self.assertTrue(0.35 <= run_time < 0.45)
        self.assertEqual(results, [2])

        # Do it again, to go up one more step.

        api_call_queue_calls = [
            _throttle_twice(result=3),
        ]

        start = time.time()
        results = yield gen.multi(api_call_queue_calls)
        stop = time.time()
        run_time = stop - start

        # Delay should be up to delay_min * 2 again,
        # because it always goes down once it succeeds,
        # but total runtime should be ~0.5s:
        # (0delay_min * 2 + delay_max + delay_max).

        self.assertEqual(
            self.api_call_queue.delay,
            self.api_call_queue.delay_min * 2)
        self.assertTrue(0.5 <= run_time < 0.6)
        self.assertEqual(results, [3])

        # Now do it with successes to step back down.

        api_call_queue_calls = [
            self.api_call_queue.call(
                self._mock_api_function_sync, result=4),
            self.api_call_queue.call(
                self._mock_api_function_sync, result=5),
            self.api_call_queue.call(
                self._mock_api_function_sync, result=6),
        ]

        start = time.time()
        results = yield gen.multi(api_call_queue_calls)
        stop = time.time()
        run_time = stop - start

        # Delay should be up to 0 again.
        # Total runtime should be ~0.15s:
        # (delay_min * 2 + delay_min).

        self.assertEqual(self.api_call_queue.delay, 0)
        self.assertTrue(0.15 <= run_time < 0.25)
        self.assertEqual(results, [4, 5, 6])

    def _mock_api_function_sync(self, result='OK',
                                exception=None,
                                delay=None):
        """
        Mock a synchronous call to AWS.

        Args:
            result: Value to return.
            exception:
                If this is an exception:

                Raise instead of returning.

                If this is a list:

                Raise and pop off the first exception
                instead of returning.
                On subsequent calls, the next exception will be raised.
                If the list is exhausted, it will not raise an exception.
            delay: If set, delay before returning a result or exception.

        Returns:
            This will return `result`.
            If `result` is not set, this will return the string 'OK'.
        """
        if delay is not None:
            time.sleep(delay)
        if exception is not None:
            if isinstance(exception, Exception):
                raise exception
            elif len(exception) > 0:
                raise exception.pop(0)

        return result

    @concurrent.run_on_executor
    def _mock_api_function_async(self, *args, **kwargs):
        """
        Wrapper around _mock_api_function_sync that runs it on another thread.
        """
        return self._mock_api_function_sync(*args, **kwargs)
