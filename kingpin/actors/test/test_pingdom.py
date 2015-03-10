"""Tests for the pingdom actors"""

import mock

from tornado import testing

from kingpin.actors import pingdom
from kingpin.actors import exceptions
from kingpin.actors.test.helper import mock_tornado, tornado_value


__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'


class TestPingdomBase(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestPingdomBase, self).setUp()
        pingdom.TOKEN = 'Unittest'
        pingdom.USER = 'Unittest'
        pingdom.PASS = 'Unittest'

    @testing.gen_test
    def test_check_name(self):
        actor = pingdom.PingdomBase('Unit Test Action', {'name': 'lollipop'})

        actor._pingdom_client = mock.Mock()
        actor._pingdom_client.checks().http_get = mock_tornado(
            {'checks': [{'name': 'lollipop'}]})

        check = yield actor._get_check()

        self.assertEquals(check['name'], 'lollipop')

    @testing.gen_test
    def test_check_name_fail(self):
        actor = pingdom.PingdomBase('Unit Test Action', {'name': 'lollipop'})

        actor._pingdom_client = mock.Mock()
        actor._pingdom_client.checks().http_get = mock_tornado(
            {'checks': []})

        with self.assertRaises(exceptions.InvalidOptions):
            yield actor._get_check()


class TestPause(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestPause, self).setUp()
        pingdom.TOKEN = 'Unittest'
        pingdom.USER = 'Unittest'
        pingdom.PASS = 'Unittest'

    @testing.gen_test
    def test_execute(self):
        actor = pingdom.Pause('Unit Test Action', {'name': 'lollipop'})

        actor._pingdom_client = mock.Mock()
        actor._get_check = mock_tornado({'name': 'lollipop',
                                         'hostname': 'http://lollipop.com',
                                         'id': 'lol'})
        actor._pingdom_client.check().http_put.return_value = tornado_value()

        yield actor._execute()

        self.assertEquals(actor._get_check._call_count, 1)
        actor._pingdom_client.check.assert_called_with(check_id='lol')
        actor._pingdom_client.check().http_put.assert_called_with(
            paused='true')

    @testing.gen_test
    def test_execute_dry(self):
        actor = pingdom.Pause('Unit Test Action', {'name': 'lollipop'},
                              dry=True)

        actor._pingdom_client = mock.Mock()
        actor._get_check = mock_tornado({'name': 'lollipop',
                                         'hostname': 'http://lollipop.com',
                                         'id': 'lol'})

        yield actor._execute()

        self.assertEquals(actor._get_check._call_count, 1)
        actor._pingdom_client.check().http_put.assert_not_called()


class TestUnpause(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestUnpause, self).setUp()
        pingdom.TOKEN = 'Unittest'
        pingdom.USER = 'Unittest'
        pingdom.PASS = 'Unittest'

    @testing.gen_test
    def test_execute(self):
        actor = pingdom.Unpause('Unit Test Action', {'name': 'lollipop'})

        actor._pingdom_client = mock.Mock()
        actor._get_check = mock_tornado({'name': 'lollipop',
                                         'hostname': 'http://lollipop.com',
                                         'id': 'lol'})
        actor._pingdom_client.check().http_put.return_value = tornado_value()

        yield actor._execute()

        self.assertEquals(actor._get_check._call_count, 1)
        actor._pingdom_client.check.assert_called_with(check_id='lol')
        actor._pingdom_client.check().http_put.assert_called_with(
            paused='false')

    @testing.gen_test
    def test_execute_dry(self):
        actor = pingdom.Unpause('Unit Test Action', {'name': 'lollipop'},
                                dry=True)

        actor._pingdom_client = mock.Mock()
        actor._get_check = mock_tornado({'name': 'lollipop',
                                         'hostname': 'http://lollipop.com',
                                         'id': 'lol'})

        yield actor._execute()

        self.assertEquals(actor._get_check._call_count, 1)
        actor._pingdom_client.check().http_put.assert_not_called()
