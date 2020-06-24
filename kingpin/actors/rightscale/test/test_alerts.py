import logging
import mock

from tornado import testing
import requests

from kingpin.actors import exceptions
from kingpin.actors.rightscale import base
from kingpin.actors.rightscale import alerts
from kingpin.actors.test import helper

log = logging.getLogger(__name__)


class TestAlertsBaseActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestAlertsBaseActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = alerts.AlertsBaseActor(
            'BaseAlertActorTest', {})

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

    @testing.gen_test
    def test_find_alert_spec(self):
        fake_spec = mock.MagicMock(name='FakeSpec')
        fake_spec.soul = {'name': 'FakeSpec'}

        # Now create a fake Rightscale resource collection object and make sure
        with mock.patch.object(self.actor._client,
                               'find_by_name_and_keys') as u_mock:
            # Try a search with no exact matching
            u_mock.return_value = helper.tornado_value([fake_spec])
            ret = yield self.actor._find_alert_spec('FakeSpec', 'fake_href')
            self.assertEqual(ret[0].soul['name'], 'FakeSpec')

    @testing.gen_test
    def test_find_alert_spec_empty_result(self):
        # Now create a fake Rightscale resource collection object and make sure
        with mock.patch.object(self.actor._client,
                               'find_by_name_and_keys') as u_mock:
            # Try a search with no exact matching
            u_mock.return_value = helper.tornado_value(None)
            ret = yield self.actor._find_alert_spec('FakeSpec', 'fake_href')
            self.assertEqual(ret, None)


class TestCreateActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestCreateActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = alerts.Create(
            'Create an AlertSpec',
            {'array': 'unittestarray',
             'condition': '<',
             'description': 'test alert',
             'duration': 500,
             'escalation_name': 'critical',
             'file': '/test',
             'threshold': '500',
             'variable': 'tx',
             'name': 'newunitarray'})

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

    @testing.gen_test
    def test_invalid_inputs(self):
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor = alerts.Create(
                'Create an AlertSpec',
                {'array': 'unittestarray',
                 'condition': '<',
                 'description': 'test alert',
                 'duration': 500,
                 'file': '/test',
                 'threshold': '500',
                 'variable': 'tx',
                 'name': 'newunitarray',
                 'vote_type': 'foobar-bad-value'})

    @testing.gen_test
    def test_execute(self):
        # Mock out the array calls. Make sure that a fake array is returned
        mock_array = mock.MagicMock(name='mockarray')
        mock_array.soul = {'name': 'mockarray'}
        mock_array.href = '/href'
        self.actor._find_server_arrays = helper.mock_tornado(mock_array)

        # Mock the create_resource() call so we don't really try to do work
        mock_create_res = mock.MagicMock(name='create_resource')
        mock_create_res.return_value = helper.tornado_value()
        self.actor._client.create_resource = mock_create_res

        # Do it, then check the mock calls
        yield self.actor._execute()
        call_arg_str = str(mock_create_res.call_args_list)
        for arg in ['alert_spec[escalation_name]',
                    'alert_spec[threshold]',
                    'alert_spec[variable]',
                    'alert_spec[subject_href]',
                    'alert_spec[description]',
                    'alert_spec[file]',
                    'alert_spec[duration]',
                    'alert_spec[condition]',
                    'alert_spec[name]']:
            self.assertIn(arg, call_arg_str)

    @testing.gen_test
    def test_execute_dry(self):
        # Mock out the array calls. Make sure that a fake array is returned
        mock_array = mock.MagicMock(name='mockarray')
        mock_array.soul = {'name': 'mockarray'}
        mock_array.href = '/href'
        self.actor._find_server_arrays = helper.mock_tornado(mock_array)

        # Mock the create_resource() call so we don't really try to do work
        mock_create_res = mock.MagicMock(name='create_resource')
        mock_create_res.return_value = helper.tornado_value()
        self.actor._client.create_resource = mock_create_res

        # Do it, then check the mock calls
        self.actor._dry = True
        yield self.actor._execute()
        mock_create_res.assert_has_calls([])

    @testing.gen_test
    def test_execute_exc_422(self):
        # Mock out the array calls. Make sure that a fake array is returned
        mock_array = mock.MagicMock(name='mockarray')
        mock_array.soul = {'name': 'mockarray'}
        mock_array.href = '/href'
        self.actor._find_server_arrays = helper.mock_tornado(mock_array)

        # Mock the create_resource() call so we don't really try to do work
        msg = '422: Unprocessible entity'
        mocked_response = mock.MagicMock(name='response')
        mocked_response.status_code = 422
        exc = requests.exceptions.HTTPError(msg, response=mocked_response)
        self.actor._client.create_resource.side_effect = exc

        # Do it, then check the mock calls
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._execute()

    @testing.gen_test
    def test_execute_exc_500(self):
        # Mock out the array calls. Make sure that a fake array is returned
        mock_array = mock.MagicMock(name='mockarray')
        mock_array.soul = {'name': 'mockarray'}
        mock_array.href = '/href'
        self.actor._find_server_arrays = helper.mock_tornado(mock_array)

        # Mock the create_resource() call so we don't really try to do work
        msg = '500: Unknown error'
        mocked_response = mock.MagicMock(name='response')
        mocked_response.status_code = 500
        exc = requests.exceptions.HTTPError(msg, response=mocked_response)
        self.actor._client.create_resource.side_effect = exc

        # Do it, then check the mock calls
        with self.assertRaises(requests.exceptions.HTTPError):
            yield self.actor._execute()


class TestDestroyActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestDestroyActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = alerts.Destroy('Destroy the AlertSpec',
                                    {'array': 'unittestarray',
                                     'name': 'alertspec'})

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

    @testing.gen_test
    def test_execute(self):
        # Mock out the array calls. Make sure that a fake array is returned
        mock_array = mock.MagicMock(name='mockarray')
        mock_array.soul = {'name': 'mockarray'}
        mock_array.href = '/href'
        self.actor._find_server_arrays = helper.mock_tornado(mock_array)

        # Now, mock out the find_alert_spec call
        mock_alert = mock.MagicMock(name='unittest')
        mock_alert.soul = {'name': 'mockalert'}
        self.actor._find_alert_spec = helper.mock_tornado([mock_alert])

        # Finally, mock out the destroy_resource call
        destroy_mock = helper.mock_tornado([])
        self.client_mock.destroy_resource = destroy_mock

        # Do it!
        yield self.actor._execute()
        self.assertEqual(1, destroy_mock._call_count)

    @testing.gen_test
    def test_execute_dry(self):
        # Mock out the array calls. Make sure that a fake array is returned
        mock_array = mock.MagicMock(name='mockarray')
        mock_array.soul = {'name': 'mockarray'}
        mock_array.href = '/href'
        self.actor._find_server_arrays = helper.mock_tornado(mock_array)

        # Now, mock out the find_alert_spec call
        mock_alert = mock.MagicMock(name='unittest')
        mock_alert.soul = {'name': 'mockalert'}
        self.actor._find_alert_spec = helper.mock_tornado([mock_alert])

        # Finally, mock out the destroy_resource call
        destroy_mock = helper.mock_tornado()
        self.client_mock.destroy_resource = destroy_mock

        # Do it!
        self.actor._dry = True
        yield self.actor._execute()
        self.assertEqual(0, destroy_mock._call_count)

    @testing.gen_test
    def test_execute_alert_not_found(self):
        # Mock out the array calls. Make sure that a fake array is returned
        mock_array = mock.MagicMock(name='mockarray')
        mock_array.soul = {'name': 'mockarray'}
        mock_array.href = '/href'
        self.actor._find_server_arrays = helper.mock_tornado(mock_array)

        # Now, mock out the find_alert_spec call
        self.actor._find_alert_spec = helper.mock_tornado(None)

        # Finally, mock out the destroy_resource call
        destroy_mock = helper.mock_tornado()
        self.client_mock.destroy_resource = destroy_mock

        # Do it!
        with self.assertRaises(alerts.AlertSpecNotFound):
            yield self.actor._execute()
        self.assertEqual(0, destroy_mock._call_count)


class TestAlertSpecBase(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestAlertSpecBase, self).setUp()
        base.TOKEN = 'unittest'

        self._spec = {
            'name': 'high load alarm',
            'description': 'My test alert',
            'escalation_name': 'critical',
            'file': 'cpu-0/cpu-idle',
            'variable': 'value',
            'condition': '>=',
            'duration': 5,
            'threshold': '0.3',
            'vote_tag': 'array_1',
            'vote_type': 'grow'
        }

        # Create the actor
        self.actor = alerts.AlertSpecBase(
            options={
                'href': '/api/template/abcd',
                'spec': self._spec,
            }
        )

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

    @testing.gen_test
    def test_precache(self):
        fake_spec = mock.MagicMock(name='fake_spec')
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(fake_spec)]
        yield self.actor._precache()
        self.assertEqual(self.actor.existing_spec, fake_spec)

    @testing.gen_test
    def test_precache_too_many_matching(self):
        fake_spec = mock.MagicMock(name='fake_spec')
        fake_spec.soul = {'name': 'high load alarm'}
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value([
                fake_spec, fake_spec
            ])
        ]
        yield self.actor._precache()
        self.assertEqual(self.actor.existing_spec, fake_spec)

    @testing.gen_test
    def test_precache_missing(self):
        fake_spec = None
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(fake_spec)]
        yield self.actor._precache()
        self.assertEqual(self.actor.existing_spec, fake_spec)

    @testing.gen_test
    def test_get_state(self):
        self.actor.existing_spec = mock.MagicMock()
        ret = yield self.actor._get_state()
        self.assertEqual(ret, 'present')

        self.actor.existing_spec = None
        ret = yield self.actor._get_state()
        self.assertEqual(ret, 'absent')

    @testing.gen_test
    def test_set_state_present(self):
        self.actor._create_spec = mock.MagicMock()
        self.actor._create_spec.side_effect = [helper.tornado_value(None)]
        yield self.actor._set_state()
        self.assertTrue(self.actor._create_spec.called)

    @testing.gen_test
    def test_set_state_absent(self):
        self.actor._delete_spec = mock.MagicMock()
        self.actor._delete_spec.side_effect = [helper.tornado_value(None)]
        self.actor._options['state'] = 'absent'
        yield self.actor._set_state()
        self.assertTrue(self.actor._delete_spec.called)

    @testing.gen_test
    def test_get_spec(self):
        self.actor.existing_spec = mock.MagicMock()
        self.actor.existing_spec.soul = {
            'created_at': 'some_time',
            'updated_at': 'some_other_time',
            'name': 'high load alarm',
            'description': 'My test alert',
            'file': 'cpu-0/cpu-idle',
            'variable': 'value',
            'condition': '>='
        }
        ret = yield self.actor._get_spec()
        self.assertEqual(
            {'name': 'high load alarm',
             'description': 'My test alert',
             'file': 'cpu-0/cpu-idle',
             'variable': 'value',
             'condition': '>='},
            ret)

    @testing.gen_test
    def test_set_spec(self):
        self.actor._update_spec = mock.MagicMock()
        self.actor._update_spec.side_effect = [helper.tornado_value(None)]
        yield self.actor._set_spec()
        self.assertTrue(self.actor._update_spec.called)

    @testing.gen_test
    def test_create_spec(self):
        fake_spec = mock.MagicMock()
        self.actor.desired_params = {}
        self.client_mock.create_resource.side_effect = [
            helper.tornado_value(fake_spec)
        ]
        yield self.actor._create_spec()
        self.assertEqual(self.actor.existing_spec, fake_spec)

    @testing.gen_test
    def test_create_spec_422(self):
        self.actor.desired_params = {}

        # Mock the create_resource() call so we don't really try to do work
        msg = '422: Unprocessible entity'
        mocked_response = mock.MagicMock(name='response')
        mocked_response.status_code = 422
        exc = requests.exceptions.HTTPError(msg, response=mocked_response)
        self.actor._client.create_resource.side_effect = exc

        # Do it, then check the mock calls
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._create_spec()

    @testing.gen_test
    def test_create_spec_500(self):
        self.actor.desired_params = {}

        # Mock the create_resource() call so we don't really try to do work
        msg = '500: Server Error'
        mocked_response = mock.MagicMock(name='response')
        mocked_response.status_code = 500
        exc = requests.exceptions.HTTPError(msg, response=mocked_response)
        self.actor._client.create_resource.side_effect = exc

        # Do it, then check the mock calls
        with self.assertRaises(requests.exceptions.HTTPError):
            yield self.actor._create_spec()

    @testing.gen_test
    def test_update_spec(self):
        fake_spec = mock.MagicMock()
        self.actor.existing_spec = mock.MagicMock()
        self.actor.desired_params = {}
        self.client_mock.update.side_effect = [
            helper.tornado_value(fake_spec)
        ]
        yield self.actor._update_spec()
        self.assertEqual(self.actor.existing_spec, fake_spec)

    @testing.gen_test
    def test_update_spec_422(self):
        self.actor.desired_params = {}
        self.actor.existing_spec = mock.MagicMock()

        # Mock the update_resource() call so we don't really try to do work
        msg = '422: Unprocessible entity'
        mocked_response = mock.MagicMock(name='response')
        mocked_response.status_code = 422
        exc = requests.exceptions.HTTPError(msg, response=mocked_response)
        self.actor._client.update.side_effect = exc

        # Do it, then check the mock calls
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._update_spec()

    @testing.gen_test
    def test_update_spec_500(self):
        self.actor.desired_params = {}
        self.actor.existing_spec = mock.MagicMock()

        # Mock the update_resource() call so we don't really try to do work
        msg = '500: Server Error'
        mocked_response = mock.MagicMock(name='response')
        mocked_response.status_code = 500
        exc = requests.exceptions.HTTPError(msg, response=mocked_response)
        self.actor._client.update.side_effect = exc

        # Do it, then check the mock calls
        with self.assertRaises(requests.exceptions.HTTPError):
            yield self.actor._update_spec()

    @testing.gen_test
    def test_delete_spec(self):
        self.actor.existing_spec = mock.MagicMock()
        self.client_mock.destroy_resource.side_effect = [
            helper.tornado_value(None)
        ]
        yield self.actor._delete_spec()
        self.assertEqual(self.actor.existing_spec, None)


class TestAlertSpecsBase(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestAlertSpecsBase, self).setUp()
        base.TOKEN = 'unittest'

        self._spec = {
            'name': 'high load alarm',
            'description': 'My test alert',
            'escalation_name': 'critical',
            'file': 'cpu-0/cpu-idle',
            'variable': 'value',
            'condition': '>=',
            'duration': 5,
            'threshold': '0.3',
            'vote_tag': 'array_1',
            'vote_type': 'grow'
        }

        # Create the actor. Mock out any calls to create an AlertSpecBase
        # object and instead return fake object instead.
        with mock.patch.object(alerts, "AlertSpecBase") as a_mock:
            a_mock()._precache.side_effect = [helper.tornado_value(None)]

            self.actor = alerts.AlertSpecsBase(
                options={
                    'href': '/api/template/abcd',
                    'specs': [self._spec],
                }
            )

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

    @testing.gen_test
    def test_precache(self):
        unwanted_fake_spec = mock.MagicMock(name='unwanted_fake_spec')
        unwanted_fake_spec.soul = {
            'name': 'unwanted spec that should be deleted'
        }
        wanted_fake_spec = mock.MagicMock(name='wanted_fake_spec')
        wanted_fake_spec.soul = {
            'name': 'high load alarm'
        }
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value([unwanted_fake_spec, wanted_fake_spec])
        ]
        with mock.patch.object(alerts, "AlertSpecBase") as a_mock:
            a_mock()._precache.side_effect = [helper.tornado_value(None)]
            yield self.actor._precache()

        self.assertEqual(2, len(self.actor.alert_actors))

        self.assertTrue(self.actor.alert_actors[0]._precache.called)
        self.assertTrue(self.actor.alert_actors[1]._precache.called)

    @testing.gen_test
    def test_precache_only_one_returned(self):
        wanted_fake_spec = mock.MagicMock(name='wanted_fake_spec')
        wanted_fake_spec.soul = {
            'name': 'high load alarm'
        }
        self.client_mock.find_by_name_and_keys.side_effect = [
            helper.tornado_value(wanted_fake_spec)
        ]
        with mock.patch.object(alerts, "AlertSpecBase") as a_mock:
            a_mock()._precache.side_effect = [helper.tornado_value(None)]
            yield self.actor._precache()

        self.assertEqual(1, len(self.actor.alert_actors))

        self.assertTrue(self.actor.alert_actors[0]._precache.called)

    @testing.gen_test
    def test_get_state(self):
        ret = yield self.actor._get_state()
        self.assertEqual(None, ret)

    @testing.gen_test
    def test_compare_state(self):
        self.actor.alert_actors[0]._compare_state.side_effect = [
            helper.tornado_value(False)]

        ret = yield self.actor._compare_state()
        self.assertEqual(False, ret)

    @testing.gen_test
    def test_set_state(self):
        test_actor = self.actor.alert_actors[0]
        test_actor._compare_state.side_effect = [helper.tornado_value(False)]
        test_actor._set_state.side_effect = [helper.tornado_value(None)]

        yield self.actor._set_state()

        self.assertTrue(test_actor._set_state.called)
        self.assertTrue(self.actor.changed)

    @testing.gen_test
    def test_get_specs(self):
        self.actor.alert_actors[0]._get_spec.side_effect = [
            helper.tornado_value(1)]
        ret = yield self.actor._get_specs()
        self.assertEqual([1], ret)

    @testing.gen_test
    def test_set_specs(self):
        test_actor = self.actor.alert_actors[0]
        test_actor._compare_spec.side_effect = [helper.tornado_value(False)]
        test_actor._execute.side_effect = [helper.tornado_value(None)]

        yield self.actor._set_specs()

        self.assertTrue(test_actor._execute.called)
        self.assertTrue(self.actor.changed)
