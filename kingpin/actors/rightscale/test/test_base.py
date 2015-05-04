import logging
# import mock

from tornado import testing

from kingpin.actors import exceptions
from kingpin.actors.rightscale import base

log = logging.getLogger(__name__)


class TestRightScaleBaseActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestRightScaleBaseActor, self).setUp()
        base.TOKEN = 'unittest'

    @testing.gen_test
    def test_init_without_environment_creds(self):
        # Un-set the token and make sure the init fails
        base.TOKEN = None
        with self.assertRaises(exceptions.InvalidCredentials):
            base.RightScaleBaseActor('Unit Test Action', {})

    def test_generate_rightscale_params_with_invalid_params(self):
        actor = base.RightScaleBaseActor('Unit Test Action', {})
        with self.assertRaises(exceptions.InvalidOptions):
            actor._generate_rightscale_params('test', ['a', 'b'])

        with self.assertRaises(exceptions.InvalidOptions):
            actor._generate_rightscale_params('test', 'foo')

    def test_generate_rightscale_params(self):
        params = {'name': 'unittest-name',
                  'status': 'enabled',
                  'elasticity_params': {
                      'bounds': {
                          'min_count': 3,
                          'max_count': 10}}}
        expected_params = [
            ('server_array[status]', 'enabled'),
            ('server_array[name]', 'unittest-name'),
            ('server_array[elasticity_params][bounds][max_count]', 10),
            ('server_array[elasticity_params][bounds][min_count]', 3)]

        actor = base.RightScaleBaseActor('Unit Test Action', {})
        ret = actor._generate_rightscale_params('server_array', params)

        self.assertItemsEqual(expected_params, ret)

    def test_generate_rightscale_params_with_array(self):
        self.maxDiff = None
        params = {'name': 'unittest-name',
                  'status': 'enabled',
                  'elasticity_params': {
                      'schedule': [
                          {'day': 'Sunday', 'max_count': 2,
                           'min_count': 1, 'time': '07:00'},
                          {'day': 'Monday', 'max_count': 2,
                           'min_count': 1, 'time': '07:00'},
                          {'day': 'Tuesday', 'max_count': 2,
                           'min_count': 1, 'time': '07:00'}
                      ]
                  }}
        expected_params = [
            ('server_array[status]', 'enabled'),
            ('server_array[name]', 'unittest-name'),

            ('server_array[elasticity_params][schedule][][day]', 'Sunday'),
            ('server_array[elasticity_params][schedule][][max_count]', 2),
            ('server_array[elasticity_params][schedule][][min_count]', 1),
            ('server_array[elasticity_params][schedule][][time]', '07:00'),

            ('server_array[elasticity_params][schedule][][day]', 'Monday'),
            ('server_array[elasticity_params][schedule][][max_count]', 2),
            ('server_array[elasticity_params][schedule][][min_count]', 1),
            ('server_array[elasticity_params][schedule][][time]', '07:00'),

            ('server_array[elasticity_params][schedule][][day]', 'Tuesday'),
            ('server_array[elasticity_params][schedule][][max_count]', 2),
            ('server_array[elasticity_params][schedule][][min_count]', 1),
            ('server_array[elasticity_params][schedule][][time]', '07:00')
        ]

        actor = base.RightScaleBaseActor('Unit Test Action', {})
        ret = actor._generate_rightscale_params('server_array', params)

        self.assertItemsEqual(expected_params, ret)
