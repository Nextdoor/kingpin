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
        self.assertEquals(
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
        self.assertEquals(
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
        self.assertEquals(
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
        self.assertEquals(
            ('Spotinst Request ID (fake_id) GET /fake: '
             '{u\'something\': u\'else\'}'),
            str(fake_exc))


class TestSpotinstBase(testing.AsyncTestCase):

    """Unit tests for the packagecloud Base actor."""

    def setUp(self, *args, **kwargs):
        super(TestSpotinstBase, self).setUp(*args, **kwargs)
        spotinst.TOKEN = 'Unittest'
        spotinst.DEBUG = True

    def test_init_with_debug_disabled(self):
        spotinst.DEBUG = False
        spotinst.SpotinstBase('Unit Test Action', {})
        self.assertEquals(
            20, logging.getLogger('tornado_rest_client.api').level)

    def test_init_missing_token(self):
        # Un-set the token and make sure the init fails
        spotinst.TOKEN = None
        with self.assertRaises(exceptions.InvalidCredentials):
            spotinst.SpotinstBase('Unit Test Action', {})


class TestElastiGroup(testing.AsyncTestCase):

    """Unit tests for the ElastiGroup actor."""

    def setUp(self, *args, **kwargs):
        super(TestElastiGroup, self).setUp(*args, **kwargs)
        file = 'examples/test/spotinst.elastigroup/unittest.json'
        spotinst.TOKEN = 'Unittest'

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

    def test_parse_group_config(self):
        self.assertEquals(
            (self.actor._config['group']['compute']
             ['availabilityZones'][0]['name']), 'us-test-1a')
        self.assertEquals(
            self.actor._config['group']['name'], 'unittest')

    def test_parse_group_config_no_config(self):
        self.actor._options['config'] = None
        self.assertEquals(
            None, self.actor._parse_group_config())

    def test_parse_group_config_missing_token(self):
        del(self.actor._init_tokens['ZONE'])
        with self.assertRaises(exceptions.InvalidOptions):
            self.actor._parse_group_config()

    def test_parse_group_with_b64_data(self):
        file = 'examples/test/spotinst.elastigroup/unittest.b64.json'
        init_tokens = {
            'SECGRP': 'sg-123123',
            'ZONE': 'us-test-1a',
            'SUBNET': 'sn-123123'
        }
        self.actor = spotinst.ElastiGroup(
            'unittest',
            {'name': 'unittest', 'config': file},
            init_tokens=init_tokens)
        self.actor._client = mock.Mock()

        self.assertEquals(
            'IyEvYmluL2Jhc2gKZWNobyBEb25l',
            (self.actor._config['group']['compute']
             ['launchSpecification']['userData']))

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
        self.assertEquals(
            ret, [{'group': {'name': 'test'}}])

    @testing.gen_test
    def test_get_group(self):
        matching_group = {
            'name': 'unittest',
            'id': 'bogus',
        }
        self.actor._list_groups = mock_tornado([matching_group])

        ret = yield self.actor._get_group()
        self.assertEquals(ret, {'group': matching_group})

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
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_get_group_no_matching_groups(self):
        unmatching_group = {
            'name': 'unittest-not-matching',
            'id': 'bogus',
        }
        self.actor._list_groups = mock_tornado([unmatching_group])
        ret = yield self.actor._get_group()
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_precache(self):
        fake_group = {
            'name': 'unittest',
            'id': 'bogus'
        }
        self.actor._get_group = mock_tornado(fake_group)
        self.actor._validate_group = mock_tornado(None)
        yield self.actor._precache()
        self.assertEquals(fake_group, self.actor._group)

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
        self.assertEquals('present', ret)

    @testing.gen_test
    def test_get_state_false(self):
        self.actor._group = None
        ret = yield self.actor._get_state()
        self.assertEquals('absent', ret)

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

        # Mock out the _precache method which is called again after the
        # create_group API call is made.
        self.actor._precache = mock_tornado(None)

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
        self.assertEquals(True, ret)

        # Now, lets modify the ElastiGroup config a bit.. the diff should
        # return false.
        self.actor._group['group']['description'] = 'new description'
        ret = yield self.actor._compare_config()
        self.assertEquals(False, ret)

    @testing.gen_test
    def test_compare_config_not_existing(self):
        # Pretend that the group doesn't exist at all in Spotinst
        self.actor._group = None

        # This should return True because the config simply doesnt exist in
        # Spotinst. The _set_state() method will create it during a real run.
        ret = yield self.actor._compare_config()
        self.assertEquals(True, ret)

    @testing.gen_test
    def test_get_config(self):
        self.actor._group = 1
        ret = yield self.actor._get_config()
        self.assertEquals(1, ret)

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
        self.assertEquals(self.actor._group, {'group': 'object'})

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
