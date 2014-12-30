"""Tests for the misc actors"""

import time

from tornado import testing

from kingpin.actors import exceptions
from kingpin.actors import misc


__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'


class IntegrationGenericHTTP(testing.AsyncTestCase):

    integration = True

    @testing.gen_test(timeout=60)
    def integration_get(self):
        actor = misc.GenericHTTP('Test', {'url': 'http://httpbin.org/get'})

        yield actor.execute()

    @testing.gen_test(timeout=60)
    def integration_post(self):
        actor = misc.GenericHTTP('Test', {
            'url': 'http://httpbin.org/post',
            'data': {'foo': 'bar'}})

        yield actor.execute()

    @testing.gen_test(timeout=60)
    def integration_auth(self):
        actor = misc.GenericHTTP('Test', {
            'url': 'http://httpbin.org/basic-auth/unit/test',
            'username': 'unit',
            'password': 'test'})

        yield actor.execute()

    @testing.gen_test(timeout=60)
    def integration_auth_fail(self):
        actor = misc.GenericHTTP('Test', {
            'url': 'http://httpbin.org/basic-auth/unit/test',
            'username': 'wrong',
            'password': 'pass'})

        with self.assertRaises(exceptions.InvalidCredentials):
            yield actor.execute()


class IntegrationMacro(testing.AsyncTestCase):

    integration = True

    @testing.gen_test
    def integration_execute(self):
        actor = misc.Macro('Test', {
            'macro': 'examples/test/sleep.json'})

        start = time.time()
        yield actor.execute()
        end = time.time()
        runtime = end - start
        self.assertTrue(runtime > 0.1)

    @testing.gen_test
    def integration_execute_remote(self):
        misc.Macro('Test', {
            'macro': 'https://raw.githubusercontent.com/Nextdoor/kingpin/'
                     'macro_actor/examples/test/sleep.json'})

    @testing.gen_test
    def integration_execute_dry(self):
        actor = misc.Macro('Test', {
            'macro': 'examples/test/sleep.json'},
            dry=True)

        start = time.time()
        yield actor.execute()
        end = time.time()
        runtime = end - start
        self.assertTrue(runtime < 0.1)
