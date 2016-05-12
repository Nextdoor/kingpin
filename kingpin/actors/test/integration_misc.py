"""Tests for the misc actors"""

import os
import time

from nose.plugins.attrib import attr

from tornado import testing

from kingpin.actors import exceptions
from kingpin.actors import misc


__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'


class IntegrationGenericHTTP(testing.AsyncTestCase):

    integration = True

    @attr('http', 'integration')
    @testing.gen_test(timeout=60)
    def integration_get(self):
        actor = misc.GenericHTTP('Test', {'url': 'http://httpbin.org/get'})

        yield actor.execute()

    @attr('http', 'integration')
    @testing.gen_test(timeout=60)
    def integration_post(self):
        actor = misc.GenericHTTP('Test', {
            'url': 'http://httpbin.org/post',
            'data': {'foo': 'bar'}})

        yield actor.execute()

    @attr('http', 'integration')
    @testing.gen_test(timeout=60)
    def integration_auth(self):
        actor = misc.GenericHTTP('Test', {
            'url': 'http://httpbin.org/basic-auth/unit/test',
            'username': 'unit',
            'password': 'test'})

        yield actor.execute()

    @attr('http', 'integration')
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

    @attr('http', 'integration')
    @testing.gen_test
    def integration_execute(self):
        actor = misc.Macro('Test', {
            'macro': 'examples/test/sleep.json',
            'tokens': dict(os.environ)})

        start = time.time()
        yield actor.execute()
        end = time.time()
        runtime = end - start
        self.assertTrue(runtime > 0.1)

    @attr('http', 'integration')
    @testing.gen_test
    def integration_fail_without_env(self):
        # Actor should fail if tokens aren't passed for env. variables.
        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            misc.Macro('Test', {'macro': 'examples/test/sleep.json'},
                       init_tokens={})

    @attr('http', 'integration')
    @testing.gen_test
    def integration_execute_remote(self):
        gh_src = 'https://raw.githubusercontent.com/Nextdoor/kingpin/master'
        # Successful __init__ on this actor validates downloading and parsing.
        misc.Macro('Test', {
            'macro': gh_src + '/examples/test/sleep.json',
            'tokens': dict(os.environ)})

    @attr('http', 'integration', 'dry')
    @testing.gen_test
    def integration_execute_dry(self):
        actor = misc.Macro('Test', {
            'macro': 'examples/test/sleep.json',
            'tokens': dict(os.environ)},
            dry=True)

        start = time.time()
        yield actor.execute()
        end = time.time()
        runtime = end - start
        self.assertTrue(runtime < 0.1)
