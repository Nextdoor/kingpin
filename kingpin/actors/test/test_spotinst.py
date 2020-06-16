import copy
import mock
import logging
import json

from tornado import testing
from tornado import httpclient

from kingpin.actors import exceptions
from kingpin.actors import spotinst
from kingpin.actors.test.helper import mock_tornado, tornado_value

__author__ = 'Matt Wise <matt@nextdoor.com>'


class TestSpotinstException(testing.AsyncTestCase):

    def test_no_json_in_body(self):
        fake_body = '400 Bad Mmmkay'
        exc = spotinst.SpotinstException(fake_body)
        self.assertEqual(
            'Unknown error: 400 Bad Mmmkay',
            str(exc))

    def test_invalid_auth_response(self):
        fake_resp_body = mock.MagicMock(name='response_body')
        fake_resp_body.body = json.dumps(
            {
                'request': {
                    'id': 'fake_id',
                    'url': '/fake',
                    'method': 'GET',
                    'timestamp': '2016-12-28T22:36:36.324Z',
                },
                'response': {
                    'error': 'invalid auth',
                    'error_id': 'NOAUTH'
                },
            }
        )
        source_exc = httpclient.HTTPError(
            400, '400 Bad Request', fake_resp_body)
        fake_exc = spotinst.SpotinstException(source_exc)
        self.assertEqual(
            'Spotinst Request ID (fake_id) GET /fake: invalid auth',
            str(fake_exc))

    def test_group_validation_errors(self):
        fake_resp_body = mock.MagicMock(name='response_body')
        fake_resp_body.body = json.dumps(
            {
                'request': {
                    'id': 'fake_id',
                    'url': '/fake',
                    'method': 'GET',
                    'timestamp': '2016-12-28T22:36:36.324Z',
                },
                'response': {
                    'errors': [
                        {'message': 'Cant create spot requests.',
                         'code': 'GENERAL_ERROR'},
                        {'message': 'AMI ami-16fc4976 with an...',
                         'code': 'UnsupportedOperation'},
                    ]
                },
            }
        )
        source_exc = httpclient.HTTPError(
            400, '400 Bad Request', fake_resp_body)
        fake_exc = spotinst.SpotinstException(source_exc)
        self.assertEqual(
            ('Spotinst Request ID (fake_id) GET /fake: GENERAL_ERROR: Cant '
             'create spot requests., UnsupportedOperation: AMI ami-16fc4976 '
             'with an...'),
            str(fake_exc))

    def test_unknown_error_body(self):
        fake_resp_body = mock.MagicMock(name='response_body')
        fake_resp_body.body = json.dumps(
            {
                'request': {
                    'id': 'fake_id',
                    'url': '/fake',
                    'method': 'GET',
                    'timestamp': '2016-12-28T22:36:36.324Z',
                },
                'response': {
                    'something': 'else'
                },
            }
        )
        source_exc = httpclient.HTTPError(
            400, '400 Bad Request', fake_resp_body)
        fake_exc = spotinst.SpotinstException(source_exc)
        self.assertEqual(
            ('Spotinst Request ID (fake_id) GET /fake: '
             '{\'something\': \'else\'}'),
            str(fake_exc))


class TestSpotinstBase(testing.AsyncTestCase):

    """Unit tests for the packagecloud Base actor."""

    def setUp(self, *args, **kwargs):
        super(TestSpotinstBase, self).setUp(*args, **kwargs)
        spotinst.TOKEN = 'Unittest'
        spotinst.DEBUG = True
        spotinst.ACCOUNT_ID = 'act-test'

    def test_init_with_debug_disabled(self):
        spotinst.DEBUG = False
        spotinst.SpotinstBase('Unit Test Action', {})
        self.assertEqual(
            20, logging.getLogger('tornado_rest_client.api').level)

    def test_init_missing_token(self):
        spotinst.TOKEN = None
        with self.assertRaises(exceptions.InvalidCredentials):
            spotinst.SpotinstBase('Unit Test Action', {})

    def test_init_without_account_id(self):
        spotinst.ACCOUNT_ID = None
        with self.assertRaises(exceptions.InvalidCredentials):
            spotinst.SpotinstBase('Unit Test Action', {})


class TestElastiGroup(testing.AsyncTestCase):

    """Unit tests for the ElastiGroup actor."""

    def setUp(self, *args, **kwargs):
        super(TestElastiGroup, self).setUp(*args, **kwargs)
        file = 'examples/test/spotinst.elastigroup/unittest.json'
        spotinst.TOKEN = 'Unittest'
        spotinst.ACCOUNT_ID = 'act-test'

        # Manually inject some fake values for the subnet/secgrp/zone
        init_tokens = {
            'SECGRP': 'sg-123123',
            'ZONE': 'us-test-1a',
            'SUBNET': 'sn-123123'
        }

        self.actor = spotinst.ElastiGroup(
            'unittest',
            {'name': 'unittest',
             'config': file,
             'wait_on_create': True,
             'wait_on_roll': True},
            init_tokens=init_tokens)
        self.actor._client = mock.Mock()

    def test_init_with_string_roll_settings(self):
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor = spotinst.ElastiGroup(
                options={'name': 'unittest',
                         'config': 'junk',
                         'roll_batch_size': 'some_number'})

    def test_parse_group_config(self):
        self.assertEqual(
            (self.actor._config['group']['compute']
             ['availabilityZones'][0]['name']), 'us-test-1a')
        self.assertEqual(
            self.actor._config['group']['name'], 'unittest')

    def test_parse_group_config_no_config(self):
        self.actor._options['config'] = None
        self.assertEqual(
            None, self.actor._parse_group_config())

    def test_parse_group_config_missing_token(self):
        del(self.actor._init_tokens['ZONE'])
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor._parse_group_config()

    @testing.gen_test
    def test_list_groups(self):
        list_of_groups = {
            'request': {
                'id': 'fake_id',
                'url': '/fake',
                'method': 'GET',
                'timestamp': '2016-12-28T22:36:36.324Z',
            },
            'response': {
                'items': [
                    {'group': {'name': 'test'}}
                ]
            }
        }

        self.actor._client.aws.ec2.list_groups.http_get = mock_tornado(
            list_of_groups)
        ret = yield self.actor._list_groups()
        self.assertEqual(
            ret, [{'group': {'name': 'test'}}])

    @testing.gen_test
    def test_get_group(self):
        matching_group = {
            'name': 'unittest',
            'id': 'bogus',
        }
        self.actor._list_groups = mock_tornado([matching_group])

        ret = yield self.actor._get_group()
        self.assertEqual(ret, {'group': matching_group})

    @testing.gen_test
    def test_get_group_too_many_results(self):
        matching_group = {
            'name': 'unittest',
            'id': 'bogus',
        }
        self.actor._list_groups = mock_tornado(
            [matching_group, matching_group])

        with self.assertRaises(exceptions.InvalidOptions):
            yield self.actor._get_group()

    @testing.gen_test
    def test_get_group_no_groups(self):
        self.actor._list_groups = mock_tornado(None)
        ret = yield self.actor._get_group()
        self.assertEqual(ret, None)

    @testing.gen_test
    def test_get_group_no_matching_groups(self):
        unmatching_group = {
            'name': 'unittest-not-matching',
            'id': 'bogus',
        }
        self.actor._list_groups = mock_tornado([unmatching_group])
        ret = yield self.actor._get_group()
        self.assertEqual(ret, None)

    @testing.gen_test
    def test_precache(self):
        fake_group = {
            'name': 'unittest',
            'id': 'bogus',
            'group': {
                'capacity': {
                    'target': 128
                }
            }
        }
        self.actor._get_group = mock_tornado(fake_group)
        self.actor._validate_group = mock_tornado(None)
        yield self.actor._precache()

        # First make sure we stored the group
        self.assertEqual(fake_group, self.actor._group)

        # Second, make sure we overwrote the user config's [capacity][target]
        # setting with the spotinst value
        self.assertEqual(self.actor._config['group']['capacity']['target'],
                         128)

    @testing.gen_test
    def test_validate_group(self):
        fake_ret = {'ok': True}
        mock_client = mock.MagicMock()
        mock_client.http_post.return_value = tornado_value(fake_ret)
        self.actor._client.aws.ec2.validate_group = mock_client

        yield self.actor._validate_group()
        mock_client.http_post.assert_called_with(
            group=self.actor._config['group'])

    @testing.gen_test
    def test_get_state(self):
        self.actor._group = True
        ret = yield self.actor._get_state()
        self.assertEqual('present', ret)

    @testing.gen_test
    def test_get_state_false(self):
        self.actor._group = None
        ret = yield self.actor._get_state()
        self.assertEqual('absent', ret)

    @testing.gen_test
    def test_set_state_present(self):
        fake_ret = {
            'ok': True,
            'response': {
                'items': [
                    {'desc': 'new group'}
                ]
            }
        }
        mock_client = mock.MagicMock()
        mock_client.http_post.return_value = tornado_value(fake_ret)
        self.actor._client.aws.ec2.create_group = mock_client

        # Mock out the _get_group method which is called again after the
        # create_group API call is made.
        self.actor._get_group = mock_tornado(None)

        # Mock out the call to our wait_until_stable() call since thats not in
        # the scope of this test.
        self.actor._wait_until_stable = mock_tornado(None)

        yield self.actor._set_state()
        mock_client.http_post.assert_called_with(
            group=self.actor._config['group'])

    @testing.gen_test
    def test_set_state_absent(self):
        # First, lets copy the desired configuration blob. The first test,
        # we'll copy the blob and we'll ensure that they are the same.
        self.actor._group = copy.deepcopy(self.actor._config)

        # Insert some fake data that would normally have been returned in the
        # included blob from Spotinst.
        self.actor._group['group']['id'] = 'sig-1234123'
        self.actor._group['group']['createdAt'] = 'timestamp'
        self.actor._group['group']['updatedAt'] = 'timestamp'

        fake_ret = {'ok': True}
        self.actor._options['state'] = 'absent'
        mock_client = mock.MagicMock()
        mock_client.http_delete.return_value = tornado_value(fake_ret)
        self.actor._client.aws.ec2.delete_group.return_value = mock_client

        yield self.actor._set_state()
        mock_client.http_delete.assert_called_with()

    @testing.gen_test
    def test_compare_config(self):
        # First, lets copy the desired configuration blob. The first test,
        # we'll copy the blob and we'll ensure that they are the same.
        self.actor._group = copy.deepcopy(self.actor._config)

        # Insert some fake data that would normally have been returned in the
        # included blob from Spotinst.
        self.actor._group['group']['id'] = 'sig-1234123'
        self.actor._group['group']['createdAt'] = 'timestamp'
        self.actor._group['group']['updatedAt'] = 'timestamp'

        # This should return True because the configs are identical..
        ret = yield self.actor._compare_config()
        self.assertEqual(True, ret)

        # Now, lets modify the ElastiGroup config a bit.. the diff should
        # return false.
        self.actor._group['group']['description'] = 'new description'
        ret = yield self.actor._compare_config()
        self.assertEqual(False, ret)

    @testing.gen_test
    def test_compare_config_not_existing(self):
        # Pretend that the group doesn't exist at all in Spotinst
        self.actor._group = None

        # This should return True because the config simply doesnt exist in
        # Spotinst. The _set_state() method will create it during a real run.
        ret = yield self.actor._compare_config()
        self.assertEqual(True, ret)

    @testing.gen_test
    def test_get_config(self):
        self.actor._group = 1
        ret = yield self.actor._get_config()
        self.assertEqual(1, ret)

    @testing.gen_test
    def test_set_config(self):
        # First, lets copy the desired configuration blob. The first test,
        # we'll copy the blob and we'll ensure that they are the same.
        self.actor._group = copy.deepcopy(self.actor._config)

        # Insert some fake data that would normally have been returned in the
        # included blob from Spotinst.
        self.actor._group['group']['id'] = 'sig-1234123'
        self.actor._group['group']['createdAt'] = 'timestamp'
        self.actor._group['group']['updatedAt'] = 'timestamp'

        # Pretend to roll the group if a change is made
        self.actor._options['roll_on_change'] = True
        self.actor._roll_group = mock.MagicMock()
        self.actor._roll_group.return_value = tornado_value(None)

        # Mock out the update_group call..
        fake_ret = {
            'response': {
                'items': [
                    {'group': 'object'}
                ]
            }
        }
        mock_client = mock.MagicMock()
        mock_client.http_put.return_value = tornado_value(fake_ret)
        self.actor._client.aws.ec2.update_group.return_value = mock_client

        yield self.actor._set_config()

        mock_client.http_put.assert_called_with(
            group=self.actor._config['group'])
        self.assertEqual(self.actor._group['group'], {'group': 'object'})
        self.actor._roll_group.assert_has_calls([mock.call])

    @testing.gen_test
    def test_roll_group(self):
        # First, lets copy the desired configuration blob. The first test,
        # we'll copy the blob and we'll ensure that they are the same.
        self.actor._group = copy.deepcopy(self.actor._config)

        # Insert some fake data that would normally have been returned in the
        # included blob from Spotinst.
        self.actor._group['group']['id'] = 'sig-1234123'
        self.actor._group['group']['createdAt'] = 'timestamp'
        self.actor._group['group']['updatedAt'] = 'timestamp'

        # Mock out the returned calls from Spotinst. The first time we call the
        # roll status method, we'll return no rolls in progress. The second
        # time, there will be a single roll in progress (pretending that the
        # roll_group call was successful), and then the third time it will
        # return no rolls in progress again (pretending that we're done).
        in_progress = {
            "id": "sbgd-44e6d801",
            "status": "in_progress",
            "progress": {
                "unit": "percent",
                "value": 0
            },
            "createdAt": "2017-01-05T15:48:28.000+0000",
            "updatedAt": "2017-01-05T15:49:15.000+0000"
        }
        finished = {
            "id": "sbgd-9f1aa4f6",
            "status": "finished",
            "progress": {
                "unit": "percent",
                "value": 100
            },
            "createdAt": "2017-01-05T15:06:25.000+0000",
            "updatedAt": "2017-01-05T15:22:17.000+0000"
        }

        roll_responses = [
            # First response, no rolls are in progress
            tornado_value({
                "request": {
                    "id": "request-1-no-in-progress",
                    "url": "/aws/ec2/group/sig-b55014f1/roll?limit=5",
                    "method": "GET",
                    "timestamp": "2017-01-05T15:50:44.215Z"
                },
                "response": {
                    "status": {
                        "code": 200,
                        "message": "OK"
                    },
                    "kind": "spotinst:aws:ec2:group:roll",
                    "items": [finished]
                }
            }),

            # Ok now pretend that one roll is in progress, and one is finished
            tornado_value({
                "request": {
                    "id": "request-2-one-in-progress",
                    "url": "/aws/ec2/group/sig-b55014f1/roll?limit=5",
                    "method": "GET",
                    "timestamp": "2017-01-05T15:50:44.215Z"
                },
                "response": {
                    "status": {
                        "code": 200,
                        "message": "OK"
                    },
                    "kind": "spotinst:aws:ec2:group:roll",
                    "items": [in_progress, finished]
                }
            }),

            # Finally, no rolls in progress.
            tornado_value({
                "request": {
                    "id": "request-3-none-in-progress",
                    "url": "/aws/ec2/group/sig-b55014f1/roll?limit=5",
                    "method": "GET",
                    "timestamp": "2017-01-05T15:50:44.215Z"
                },
                "response": {
                    "status": {
                        "code": 200,
                        "message": "OK"
                    },
                    "kind": "spotinst:aws:ec2:group:roll",
                    "items": [finished, finished]
                }
            })
        ]

        # Generate a basic mock object for the entire 'roll' RestConsumer. Mock
        # out the http_get() method to return back the three fake responses
        # above. Mock out the http_put() method to just return safely.
        roll_mock = mock.MagicMock()
        roll_mock.http_get.side_effect = roll_responses
        roll_mock.http_put.side_effect = [tornado_value(None)]
        self.actor._client.aws.ec2.roll.return_value = roll_mock

        # Make the call, and make sure we wait for all roll operations to
        # finish
        self.actor._options['wait_on_roll'] = True
        yield self.actor._roll_group(delay=0.01)

        # Now verify that all the calls were made to the roll_mock
        roll_mock.assert_has_calls([
            mock.call.http_get(),
            mock.call.http_put(gracePeriod=600, batchSizePercentage=20),
            mock.call.http_get(),
            mock.call.http_get(),
        ])

    @testing.gen_test
    def test_wait_until_stable(self):
        # First, lets copy the desired configuration blob. The first test,
        # we'll copy the blob and we'll ensure that they are the same.
        self.actor._group = copy.deepcopy(self.actor._config)

        # Insert some fake data that would normally have been returned in the
        # included blob from Spotinst.
        self.actor._group['group']['id'] = 'sig-1234123'
        self.actor._group['group']['createdAt'] = 'timestamp'
        self.actor._group['group']['updatedAt'] = 'timestamp'

        # Mock out what a pending vs fulfilled instance looks like
        pending = {
            'spotInstanceRequestId': 'sir-n8688grq',
            'instanceId': None,
            'instanceType': 't1.micro',
            'product': 'Linux/UNIX (Amazon VPC)',
            'availabilityZone': 'us-west-2a',
            'createdAt': '2017-01-03T22:30:56.000Z',
            'status': 'pending-evaluation'
        }
        fullfilled = {
            'spotInstanceRequestId': 'sir-n8688grq',
            'instanceId': 'i-abcdefg',
            'instanceType': 't1.micro',
            'product': 'Linux/UNIX (Amazon VPC)',
            'availabilityZone': 'us-west-2a',
            'createdAt': '2017-01-03T22:30:56.000Z',
            'status': 'fullfilled'
        }

        # Create a mock for the group_status API call that returns different
        # results on the 3rd time its called. The first two times, the
        # instances will be in a pending-evaluation state, the third call they
        # will be in a fullfilled state.
        group_status_mock = mock.MagicMock('group_status')
        self.actor._client.aws.ec2.group_status().http_get = group_status_mock
        self.actor._client.aws.ec2.group_status().http_get.side_effect = [
            tornado_value({'response': {'items': [pending, pending]}}),
            tornado_value({'response': {'items': [pending, pending]}}),
            tornado_value({'response': {'items': [fullfilled, fullfilled]}}),
        ]

        # Now make the call
        yield self.actor._wait_until_stable(delay=0.01)
        group_status_mock.assert_has_calls([mock.call(), mock.call(),
                                            mock.call()])
