from future import standard_library
standard_library.install_aliases()
import logging
import urllib.request, urllib.parse, urllib.error
import json
import mock

import six.moves

from boto.exception import BotoServerError
from tornado import testing
from tornado import gen

from kingpin.actors import exceptions
from kingpin.actors.aws import settings
from kingpin.actors.aws.iam import entities

log = logging.getLogger(__name__)


@gen.coroutine
def tornado_value(*args):
    """Returns whatever is passed in. Used for testing."""
    raise gen.Return(*args)


class TestEntityBaseActor(testing.AsyncTestCase):

    def setUp(self):
        super(TestEntityBaseActor, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        six.moves.reload_module(entities)

        # Create our actor object with some basics... then mock out the IAM
        # connections..
        self.actor = entities.EntityBaseActor(
            'Unit Test',
            {'name': 'test',
             'state': 'present',
             'inline_policies': 'examples/aws.iam.user/s3_example.json'})

        iam_mock = mock.Mock()
        self.actor.iam_conn = iam_mock

        # The base class defines these as None -- but in order to test them, we
        # need to have more realistic and trackable method names.
        self.actor.entity_name = 'base'
        self.actor.create_entity = iam_mock.create_base
        self.actor.delete_entity = iam_mock.delete_base
        self.actor.delete_entity_policy = iam_mock.delete_base_policy
        self.actor.get_all_entities = iam_mock.get_all_bases
        self.actor.get_all_entity_policies = iam_mock.get_all_base_policies
        self.actor.get_entity_policy = iam_mock.get_base_policy
        self.actor.put_entity_policy = iam_mock.put_base_policy

        # Pretend like we're a more full featured actor (User/Group/Role) that
        # has inline policies. This could be abstracted differently by making
        # another BaseActor for Users/Groups/Roles thats separate from
        # InstanceProfiles -- but for now this will do.
        self.actor._parse_inline_policies(self.actor.option('inline_policies'))

    @testing.gen_test
    def test_generate_policy_name(self):
        name = '/some-?funky*-directory/with.my.policy.json'
        parsed = self.actor._generate_policy_name(name)
        self.assertEquals(parsed, 'some-funky-directory-with.my.policy')

    @testing.gen_test
    def test_get_entity_policies(self):
        policy_str = ''.join([
            '%7B%22Version%22%3A%20%222012-10-17%22%2C%20',
            '%22Statement%22%3A%20%5B%7B%22Action%22%3A%20%5B',
            '%22s3%3ACreate%2A%22%2C%20%22s3%3AGet%2A%22%2C%20',
            '%22s3%3APut%2A%22%2C%20%22s3%3AList%2A%22%5D%2C%20',
            '%22Resource%22%3A%20%5B',
            '%22arn%3Aaws%3As3%3A%3A%3Akingpin%2A%2F%2A%22%2C%20',
            '%22arn%3Aaws%3As3%3A%3A%3Akingpin%2A%22%5D%2C%20',
            '%22Effect%22%3A%20%22Allow%22%7D%5D%7D'])
        policy_dict = {
            u'Version': u'2012-10-17',
            u'Statement': [
                {u'Action': [
                    u's3:Create*',
                    u's3:Get*',
                    u's3:Put*',
                    u's3:List*'],
                 u'Resource': [
                    u'arn:aws:s3:::kingpin*/*',
                    u'arn:aws:s3:::kingpin*'],
                 u'Effect': u'Allow'}]}

        # First test, throw an exception getting the entity policies..
        a = self.actor
        a.iam_conn.get_all_base_policies.side_effect = BotoServerError(
            500, 'Yikes!')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._get_entity_policies('test')

        # Next, what if the entity doesn't exist at all?
        a.iam_conn.get_all_base_policies.side_effect = BotoServerError(
            404, 'User does not exist!')
        ret = yield self.actor._get_entity_policies('test')
        self.assertEquals(ret, {})

        # What if self.get_all_entity_policies raises a TypeError because its
        # set to None (or not set at all)?
        a.iam_conn.get_all_base_policies.side_effect = TypeError(
            'NoneType is not callable')
        ret = yield self.actor._get_entity_policies('test')
        self.assertEquals(ret, {})

        # Now unset the side effect so we can do a real test
        self.actor.iam_conn.get_all_base_policies.side_effect = None

        # Return a list of entity policy names...
        policies = {
            'list_base_policies_response': {
                'list_base_policies_result': {
                    'policy_names': ['test1', 'test2', 'test3']
                }
            }
        }
        self.actor.iam_conn.get_all_base_policies.return_value = policies

        # Now mock out the policy responses too -- each request for a policy
        # will return a single copy of the policy_str above.
        self.actor.iam_conn.get_base_policy.return_value = {
            'get_base_policy_response': {
                'get_base_policy_result': {
                    'policy_document': policy_str,
                }
            }
        }

        # Finally, make the call and see if we get all the policies
        ret = yield self.actor._get_entity_policies('test')
        self.assertEquals(len(ret), 3)
        self.assertEquals(ret['test1'], policy_dict)
        self.assertEquals(ret['test2'], policy_dict)
        self.assertEquals(ret['test3'], policy_dict)

        # One final test.. make sure we raise an exception if any of the get
        # entity policy calls fail.
        self.actor.iam_conn.get_base_policy.side_effect = BotoServerError(
            500, 'Yikes!')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._get_entity_policies('test')

    @testing.gen_test
    def test_parse_inline_policies(self):
        parsed_policy = self.actor.inline_policies[
            'examples-aws.iam.user-s3_example'
        ]
        self.assertEquals(parsed_policy['Version'], '2012-10-17')

    @testing.gen_test
    def test_parse_inline_policies_none(self):
        self.actor._parse_inline_policies(None)
        self.assertEquals(self.actor.inline_policies, None)

    @testing.gen_test
    def test_ensure_inline_policies(self):
        # First, pretend like there are a few policies in place and we're not
        # passing any in, however we are purging policies we don't manage.
        fake_pol = {
            'Policy1': {'junk': 'policy'},
            'Policy2': {'more': 'junk'},
        }
        self.actor._get_entity_policies = mock.MagicMock()
        self.actor._get_entity_policies.side_effect = [tornado_value(fake_pol)]

        # Mock out the delete_entity_policy and put_entity_policy methods
        self.actor._delete_entity_policy = mock.MagicMock()
        self.actor._delete_entity_policy.side_effect = [
            tornado_value(None), tornado_value(None)
        ]
        self.actor._put_entity_policy = mock.MagicMock()
        self.actor._put_entity_policy.side_effect = [tornado_value(None)]

        # Ensure that the new policy was pushed, and the old policies were
        # deleted
        yield self.actor._ensure_inline_policies('test')
        self.assertEquals(1, self.actor._put_entity_policy.call_count)
        self.actor._delete_entity_policy.assert_has_calls([
            mock.call('test', 'Policy1'),
            mock.call('test', 'Policy2'),
        ], any_order=True)

    @testing.gen_test
    def test_ensure_inline_policies_updated(self):
        # First, pretend like there are a few policies in place and we're not
        # passing any in, however we are purging policies we don't manage.
        fake_pol = {
            'Policy1': {'junk': 'policy'},
            'examples-aws.iam.user-s3_example': {'more': 'junk'},
        }
        self.actor._get_entity_policies = mock.MagicMock()
        self.actor._get_entity_policies.side_effect = [tornado_value(fake_pol)]
        self.actor._put_entity_policy = mock.MagicMock()
        self.actor._put_entity_policy.side_effect = [tornado_value(None)]

        yield self.actor._ensure_inline_policies('test')
        self.assertEquals(1, self.actor._put_entity_policy.call_count)

    @testing.gen_test
    def test_delete_entity_policy_dry(self):
        self.actor._dry = True
        yield self.actor._delete_entity_policy('test', 'test-policy')
        self.assertFalse(self.actor.iam_conn.delete_base_policy.called)

    @testing.gen_test
    def test_delete_entity_policy(self):
        yield self.actor._delete_entity_policy('test', 'test-policy')
        self.assertTrue(self.actor.iam_conn.delete_base_policy.called)

    @testing.gen_test
    def test_delete_entity_policy_exception(self):
        self.actor.iam_conn.delete_base_policy.side_effect = BotoServerError(
            500, 'Yikes!')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._delete_entity_policy('test', 'test-policy')

    @testing.gen_test
    def test_put_entity_policy_dry(self):
        self.actor._dry = True
        yield self.actor._put_entity_policy('test', 'test-policy', {})
        self.assertFalse(self.actor.iam_conn.put_base_policy.called)

    @testing.gen_test
    def test_put_entity_policy(self):
        yield self.actor._put_entity_policy('test', 'test-policy', {})
        self.assertTrue(self.actor.iam_conn.put_base_policy.called)

    @testing.gen_test
    def test_put_entity_policy_exception(self):
        self.actor.iam_conn.put_base_policy.side_effect = BotoServerError(
            500, 'Yikes!')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._put_entity_policy('test', 'test-policy', {})

    @testing.gen_test
    def test_get_entity(self):
        # Test a random unexpected failure
        self.actor.iam_conn.get_all_bases.side_effect = BotoServerError(
            500, 'Yikes!')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._get_entity('test')
        self.assertTrue(self.actor.iam_conn.get_all_bases.called)
        self.actor.iam_conn.get_all_bases.reset_mock()

        # Reset the side effect to None, now we're going to use return_values
        # instead
        self.actor.iam_conn.get_all_bases.side_effect = None

        # Create some valid test user objects...
        matching_entity = {
            u'path': u'/', u'create_date': u'2016-04-05T22:15:24Z',
            u'base_name': u'test', u'arn':
            u'arn:aws:iam::123123123123:base/test', u'base_id':
            u'AIDAXXCXXXXXXXXXAAC2E'}
        not_matching_entity = {
            u'path': u'/', u'create_date': u'2016-04-05T22:15:24Z',
            u'base_name': u'some-other-base', u'arn':
            u'arn:aws:iam::123123123123:base/test', u'base_id':
            u'AIDAXXCXXXXXXXXXAAC2E'}

        # Now, first test ... no 'matching' entity in the list
        self.actor.iam_conn.get_all_bases.return_value = {
            'list_bases_response': {
                'list_bases_result': {
                    'bases': [not_matching_entity, not_matching_entity]}}}
        ret = yield self.actor._get_entity('test')
        self.assertTrue(self.actor.iam_conn.get_all_bases.called)
        self.actor.iam_conn.get_all_bases.reset_mock()
        self.assertEquals(ret, None)

        # Next, lets return TOO MANY matching entities. This is bad.
        self.actor.iam_conn.get_all_bases.return_value = {
            'list_bases_response': {
                'list_bases_result': {
                    'bases': [matching_entity, matching_entity]}}}
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._get_entity('test')
        self.assertTrue(self.actor.iam_conn.get_all_bases.called)
        self.actor.iam_conn.get_all_bases.reset_mock()

        # Finally, lets return one matching and a non matching entity
        self.actor.iam_conn.get_all_bases.return_value = {
            'list_bases_response': {
                'list_bases_result': {
                    'bases': [not_matching_entity, matching_entity]}}}
        ret = yield self.actor._get_entity('test')
        self.assertTrue(self.actor.iam_conn.get_all_bases.called)
        self.actor.iam_conn.get_all_bases.reset_mock()
        self.assertEquals(ret, matching_entity)

    @testing.gen_test
    def test_ensure_entity(self):
        create_mock = mock.MagicMock(name='_create_entity')
        delete_mock = mock.MagicMock(name='_delete_entity')
        get_mock = mock.MagicMock(name='_get_entity')
        self.actor._create_entity = create_mock
        self.actor._delete_entity = delete_mock
        self.actor._get_entity = get_mock
        self.actor._create_entity.side_effect = [tornado_value(None)]
        self.actor._delete_entity.side_effect = [tornado_value(None)]
        self.actor._get_entity.side_effect = [tornado_value(None)]

        # Mock out that the entity doesn't exist, and we're creating it
        self.actor._get_entity.side_effect = [tornado_value(None)]
        yield self.actor._ensure_entity('test', 'present')
        create_mock.assert_called_with('test')
        self.assertFalse(delete_mock.called)
        create_mock.reset_mock()
        delete_mock.reset_mock()

        # Pretend like the entity already exists..
        entity = {
            'get_base_response': {
                'get_base_result': {'base': {'arn': 'fake_arn'}}
            }
        }
        self.actor._get_entity.side_effect = [tornado_value(entity)]

        # Now if we ask to create the entity, make sure we don't make those
        # calls since the entity already exists
        self.actor._get_entity.side_effect = [tornado_value(entity)]
        yield self.actor._ensure_entity('test', 'present')
        self.assertFalse(create_mock.called)
        self.assertFalse(delete_mock.called)
        create_mock.reset_mock()
        delete_mock.reset_mock()

        # Since the entity is there, lets test deleting them.. do they get
        # deleted?
        self.actor._get_entity.side_effect = [tornado_value(entity)]
        yield self.actor._ensure_entity('test', 'absent')
        self.assertFalse(create_mock.called)
        delete_mock.assert_called_with('test')
        create_mock.reset_mock()
        delete_mock.reset_mock()

        # If the entity doesn't exist, make sure we don't try to delete them
        self.actor._get_entity.side_effect = [tornado_value(None)]
        yield self.actor._ensure_entity('test', 'absent')
        self.assertFalse(create_mock.called)
        self.assertFalse(delete_mock.called)
        create_mock.reset_mock()
        delete_mock.reset_mock()

    @testing.gen_test
    def test_delete_entity(self):
        # Pretend it worked...
        self.actor.iam_conn.delete_base.return_value = None
        self.actor._get_entity_policies = mock.MagicMock()
        self.actor._get_entity_policies.side_effect = [tornado_value(['test'])]
        self.actor._delete_entity_policy = mock.MagicMock()
        self.actor._delete_entity_policy.side_effect = [tornado_value(None)]
        yield self.actor._delete_entity('test')
        self.actor.iam_conn.delete_base.assert_called_with('test')

    @testing.gen_test
    def test_delete_entity_already_deleted(self):
        # Exception raised? Handle it!
        self.actor._get_entity_policies = mock.MagicMock()
        self.actor._get_entity_policies.side_effect = [tornado_value([])]
        self.actor.iam_conn.delete_base.side_effect = BotoServerError(
            404, 'User already gone!')
        yield self.actor._delete_entity('test')
        self.actor.iam_conn.delete_base.assert_called_with('test')

    @testing.gen_test
    def test_delete_entity_other_exception(self):
        # Exception raised? Handle it!
        self.actor._get_entity_policies = mock.MagicMock()
        self.actor._get_entity_policies.side_effect = [tornado_value([])]
        self.actor.iam_conn.delete_base.side_effect = BotoServerError(
            500, 'Yikes!')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._delete_entity('test')

    @testing.gen_test
    def test_delete_entity_dry(self):
        # Make sure we did not call the delete function!
        self.actor._dry = True
        self.actor.iam_conn.delete_base.return_value = None
        yield self.actor._delete_entity('test')
        self.assertFalse(self.actor.iam_conn.delete_base.called)

    @testing.gen_test
    def test_create_entity(self):
        # Pretend it worked...
        entity = {
            'create_base_response': {
                'create_base_result': {'base': {'arn': 'fake_arn'}}
            }
        }
        self.actor.iam_conn.create_base.return_value = entity
        yield self.actor._create_entity('test')
        self.actor.iam_conn.create_base.assert_called_with('test')

    @testing.gen_test
    def test_create_entity_already_exists(self):
        self.actor.iam_conn.create_base.side_effect = BotoServerError(
            409, 'User already exists')
        yield self.actor._create_entity('test')
        self.actor.iam_conn.create_base.assert_called_with('test')

    @testing.gen_test
    def test_create_entity_other_exception(self):
        self.actor.iam_conn.create_base.side_effect = BotoServerError(
            500, 'Yikes!')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._create_entity('test')

    @testing.gen_test
    def test_create_entity_dry(self):
        # Make sure we did not call the create function!
        self.actor._dry = True
        yield self.actor._create_entity('test')
        self.assertFalse(self.actor.iam_conn.create_base.called)


class TestUser(testing.AsyncTestCase):

    def setUp(self):
        super(TestUser, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        six.moves.reload_module(entities)

        # Create our actor object with some basics... then mock out the IAM
        # connections..
        self.actor = entities.User(
            'Unit Test',
            {'name': 'test',
             'state': 'present',
             'inline_policies': 'examples/aws.iam.user/s3_example.json',
             'groups': 'foo'})

        iam_mock = mock.Mock()
        self.actor.iam_conn = iam_mock

        self.actor.create_entity = iam_mock.create_user
        self.actor.delete_entity = iam_mock.delete_user
        self.actor.delete_entity_policy = iam_mock.delete_user_policy
        self.actor.get_all_entities = iam_mock.get_all_users
        self.actor.get_all_entity_policies = iam_mock.get_all_user_policies
        self.actor.get_entity_policy = iam_mock.get_user_policy
        self.actor.put_entity_policy = iam_mock.put_user_policy

    @testing.gen_test
    def test_ensure_groups(self):
        # Mock out a fake list of groups that the user is already attached to
        fake_groups = {
            'list_groups_for_user_response': {
                'list_groups_for_user_result': {
                    'groups': [
                        {'path': '/', 'group_name': 'test-group-1'},
                        {'path': '/', 'group_name': 'test-group-2'}
                    ]
                }
            }
        }
        self.actor.iam_conn.get_groups_for_user.return_value = fake_groups

        # Create mocks for the add/remove user group methods
        self.actor._add_user_to_group = mock.MagicMock()
        self.actor._remove_user_from_group = mock.MagicMock()

        # Same as above, but now purge the unmanaged groups
        self.actor._add_user_to_group.side_effect = [
            tornado_value(None), tornado_value(None)]
        self.actor._remove_user_from_group.side_effect = [
            tornado_value(None), tornado_value(None)
        ]
        yield self.actor._ensure_groups('test', 'ng1')
        self.actor._add_user_to_group.assert_has_calls([
            mock.call('test', 'ng1')])
        self.actor._remove_user_from_group.assert_has_calls([
            mock.call('test', 'test-group-1'),
            mock.call('test', 'test-group-2')],
            any_order=True)
        self.actor._add_user_to_group.reset_mock()
        self.actor._remove_user_from_group.reset_mock()

    @testing.gen_test
    def test_ensure_groups_with_exceptions(self):
        # Create mocks for the add/remove user group methods
        self.actor._add_user_to_group = mock.MagicMock()
        self.actor._add_user_to_group.side_effect = [
            tornado_value(None),
            tornado_value(None),
        ]
        self.actor._remove_user_from_group = mock.MagicMock()
        self.actor._remove_user_from_group.side_effect = [tornado_value(None)]

        # The user doesn't exist? No problem.. we'll move forward anyways and
        # assume we're in a dry run and the user hasn't been created, and thus
        # there are no groups.
        self.actor.iam_conn.get_groups_for_user.side_effect = BotoServerError(
            404, '')
        yield self.actor._ensure_groups('test', ['ng1', 'ng2'])
        self.actor._add_user_to_group.assert_has_calls([
            mock.call('test', 'ng1'),
            mock.call('test', 'ng2')
        ], any_order=True)
        self.assertFalse(self.actor._remove_user_from_group.called)

        # Some other error happens? raise it!
        self.actor.iam_conn.get_groups_for_user.side_effect = BotoServerError(
            500, '')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._ensure_groups('test', ['ng1', 'ng2'])

    @testing.gen_test
    def test_add_user_to_group(self):
        self.actor.iam_conn.add_user_to_group.return_value = None
        yield self.actor._add_user_to_group('test', 'group')
        self.actor.iam_conn.add_user_to_group.assert_called_with(
            'group', 'test')

    @testing.gen_test
    def test_add_user_to_group_dry(self):
        self.actor.iam_conn.add_user_to_group.return_value = None
        self.actor._dry = True
        yield self.actor._add_user_to_group('test', 'group')
        self.assertFalse(self.actor.iam_conn.add_user_to_group.called)

    @testing.gen_test
    def test_add_user_to_group_exception(self):
        self.actor.iam_conn.add_user_to_group.side_effect = BotoServerError(
            500, 'Yikes')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._add_user_to_group('test', 'group')

    @testing.gen_test
    def test_remove_user_from_group(self):
        self.actor.iam_conn.remove_user_from_group.return_value = None
        yield self.actor._remove_user_from_group('test', 'group')
        self.actor.iam_conn.remove_user_from_group.assert_called_with(
            'group', 'test')

    @testing.gen_test
    def test_remove_user_from_group_dry(self):
        self.actor.iam_conn.remove_user_from_group.return_value = None
        self.actor._dry = True
        yield self.actor._remove_user_from_group('test', 'group')
        self.assertFalse(self.actor.iam_conn.remove_user_from_group.called)

    @testing.gen_test
    def test_remove_user_from_group_exception(self):
        remove_group = self.actor.iam_conn.remove_user_from_group
        remove_group.side_effect = BotoServerError(
            500, 'Yikes')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._remove_user_from_group('test', 'group')

    @testing.gen_test
    def test_execute_absent(self):
        self.actor._options['state'] = 'absent'
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)

    @testing.gen_test
    def test_execute_present(self):
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        self.actor._ensure_inline_policies = mock.MagicMock()
        self.actor._ensure_inline_policies.side_effect = [tornado_value(None)]
        self.actor._ensure_groups = mock.MagicMock()
        self.actor._ensure_groups.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)
        self.assertTrue(self.actor._ensure_inline_policies.called)
        self.assertTrue(self.actor._ensure_groups.called)

    @testing.gen_test
    def test_execute_present_no_policies_or_groups(self):
        self.actor._options['inline_policies'] = None
        self.actor._options['groups'] = None

        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]

        self.actor._ensure_inline_policies = mock.MagicMock()
        self.actor._ensure_groups = mock.MagicMock()

        yield self.actor._execute()

        self.assertTrue(self.actor._ensure_entity.called)
        self.assertFalse(self.actor._ensure_inline_policies.called)
        self.assertFalse(self.actor._ensure_groups.called)


class TestGroup(testing.AsyncTestCase):

    def setUp(self):
        super(TestGroup, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        six.moves.reload_module(entities)

        # Create our actor object with some basics... then mock out the IAM
        # connections..
        self.actor = entities.Group(
            'Unit Test',
            {'name': 'test',
             'state': 'present',
             'inline_policies': 'examples/aws.iam.user/s3_example.json'})

        iam_mock = mock.Mock()
        self.actor.iam_conn = iam_mock

        self.actor.create_entity = iam_mock.create_user
        self.actor.delete_entity = iam_mock.delete_user
        self.actor.delete_entity_policy = iam_mock.delete_user_policy
        self.actor.get_all_entities = iam_mock.get_all_users
        self.actor.get_all_entity_policies = iam_mock.get_all_user_policies
        self.actor.get_entity_policy = iam_mock.get_user_policy
        self.actor.put_entity_policy = iam_mock.put_user_policy

    @testing.gen_test
    def test_get_group_users(self):
        fake_group = {
            'get_group_response': {
                'get_group_result': {
                    'users': [
                        {'user_name': 'group1'},
                        {'user_name': 'group2'},
                    ]
                }
            }
        }
        self.actor.iam_conn.get_group.return_value = fake_group
        ret = yield self.actor._get_group_users('test')
        self.assertEquals(ret, ['group1', 'group2'])

    @testing.gen_test
    def test_get_group_users_exception(self):
        self.actor.iam_conn.get_group.side_effect = BotoServerError(
            500, 'Yikes')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._get_group_users('test')

    @testing.gen_test
    def test_get_group_users_no_users(self):
        self.actor.iam_conn.get_group.return_value = {}
        ret = yield self.actor._get_group_users('test')
        self.assertEquals(ret, [])

    @testing.gen_test
    def test_purge_group_users_false(self):
        users = ['user1', 'user2']
        self.actor._get_group_users = mock.MagicMock()
        self.actor._get_group_users.side_effect = [tornado_value(users)]

        self.actor._remove_user_from_group = mock.MagicMock()
        self.actor._remove_user_from_group.side_effect = [
            tornado_value(None), tornado_value(None)]

        yield self.actor._purge_group_users('test', False)

        self.assertFalse(self.actor._remove_user_from_group.called)

    @testing.gen_test
    def test_purge_group_users_true(self):
        users = ['user1', 'user2']
        self.actor._get_group_users = mock.MagicMock()
        self.actor._get_group_users.side_effect = [tornado_value(users)]

        self.actor._remove_user_from_group = mock.MagicMock()
        self.actor._remove_user_from_group.side_effect = [
            tornado_value(None), tornado_value(None)]

        yield self.actor._purge_group_users('test', True)

        self.actor._remove_user_from_group.assert_has_calls([
            mock.call('user1', 'test'), mock.call('user2', 'test')])

    @testing.gen_test
    def test_execute_absent(self):
        self.actor._options['state'] = 'absent'
        self.actor._purge_group_users = mock.MagicMock()
        self.actor._purge_group_users.side_effect = [tornado_value(None)]
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)
        self.assertTrue(self.actor._purge_group_users.called)

    @testing.gen_test
    def test_execute_present(self):
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_inline_policies = mock.MagicMock()
        self.actor._purge_group_users = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        self.actor._ensure_inline_policies.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)
        self.assertFalse(self.actor._purge_group_users.called)

    @testing.gen_test
    def test_execute_present_no_policies_or_groups(self):
        self.actor._options['inline_policies'] = None
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_inline_policies = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        self.actor._ensure_inline_policies.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)
        self.assertFalse(self.actor._ensure_inline_policies.called)


class TestRole(testing.AsyncTestCase):

    def setUp(self):
        super(TestRole, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        six.moves.reload_module(entities)

        # Create our actor object with some basics... then mock out the IAM
        # connections..
        self.actor = entities.Role(
            'Unit Test',
            {'name': 'test',
             'state': 'present',
             'assume_role_policy_document':
                 'examples/aws.iam.role/lambda.json',
             'inline_policies': 'examples/aws.iam.user/s3_example.json'})

        iam_mock = mock.Mock()
        self.actor.iam_conn = iam_mock

        self.actor.create_entity = iam_mock.create_role
        self.actor.delete_entity = iam_mock.delete_role
        self.actor.delete_entity_policy = iam_mock.delete_role_policy
        self.actor.get_all_entities = iam_mock.list_roles
        self.actor.get_all_entity_policies = iam_mock.list_role_policies
        self.actor.get_entity_policy = iam_mock.get_role_policy
        self.actor.put_entity_policy = iam_mock.put_role_policy

    @testing.gen_test
    def test_ensure_assume_role_doc_no_entity(self):
        fake_entity = None
        self.actor._get_entity = mock.MagicMock()
        self.actor._get_entity.side_effect = [tornado_value(fake_entity)]

        yield self.actor._ensure_assume_role_doc('test')

    @testing.gen_test
    def test_ensure_assume_role_doc_matches(self):
        request = {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow",
                           "Principal": {"Service": "lambda.amazonaws.com"},
                           "Action": "sts:AssumeRole"}]}

        lambda_string = urllib.request.pathname2url(json.dumps(request))
        fake_entity = {'assume_role_policy_document': lambda_string}
        self.actor._get_entity = mock.MagicMock()
        self.actor._get_entity.side_effect = [tornado_value(fake_entity)]
        self.actor.iam_conn.update_assume_role_policy = mock.MagicMock()

        yield self.actor._ensure_assume_role_doc('test')
        self.assertFalse(self.actor.iam_conn.update_assume_role_policy.called)

    @testing.gen_test
    def test_ensure_assume_role_doc_mismatch(self):
        request = {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow",
                           "Principal": {"Service": "ec2.amazonaws.com"},
                           "Action": "sts:AssumeRole"}]}
        ec2_string = urllib.request.pathname2url(json.dumps(request))
        fake_entity = {'assume_role_policy_document': ec2_string}
        self.actor._get_entity = mock.MagicMock()
        self.actor._get_entity.side_effect = [tornado_value(fake_entity)]
        self.actor.iam_conn.update_assume_role_policy = mock.MagicMock()
        self.actor.iam_conn.update_assume_role_policy.side_effect = [
            tornado_value(None)]

        yield self.actor._ensure_assume_role_doc('test')
        self.assertTrue(self.actor.iam_conn.update_assume_role_policy.called)

    @testing.gen_test
    def test_ensure_assume_role_doc_mismatch_dry(self):
        self.actor._dry = True
        request = {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow",
                           "Principal": {"Service": "ec2.amazonaws.com"},
                           "Action": "sts:AssumeRole"}]}
        ec2_string = urllib.request.pathname2url(json.dumps(request))
        fake_entity = {'assume_role_policy_document': ec2_string}
        self.actor._get_entity = mock.MagicMock()
        self.actor._get_entity.side_effect = [tornado_value(fake_entity)]
        self.actor.iam_conn.update_assume_role_policy = mock.MagicMock()
        self.actor.iam_conn.update_assume_role_policy.side_effect = [
            tornado_value(None)]

        yield self.actor._ensure_assume_role_doc('test')
        self.assertFalse(self.actor.iam_conn.update_assume_role_policy.called)

    @testing.gen_test
    def test_execute_absent(self):
        self.actor._options['state'] = 'absent'
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        self.actor._ensure_assume_role_doc = mock.MagicMock()
        self.actor._ensure_assume_role_doc.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)
        self.assertFalse(self.actor._ensure_assume_role_doc.called)

    @testing.gen_test
    def test_execute_no_policy(self):
        self.actor._options['assume_role_policy_document'] = None

        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        self.actor._ensure_assume_role_doc = mock.MagicMock()
        self.actor._ensure_assume_role_doc.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)
        self.assertFalse(self.actor._ensure_assume_role_doc.called)

    @testing.gen_test
    def test_execute(self):
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        self.actor._ensure_assume_role_doc = mock.MagicMock()
        self.actor._ensure_assume_role_doc.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)
        self.assertTrue(self.actor._ensure_assume_role_doc.called)


class TestInstanceProfile(testing.AsyncTestCase):

    def setUp(self):
        super(TestInstanceProfile, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        six.moves.reload_module(entities)

        # Create our actor object with some basics... then mock out the IAM
        # connections..
        self.actor = entities.InstanceProfile(
            'Unit Test',
            {'name': 'test',
             'state': 'present',
             'role': 'test'})

        iam_mock = mock.Mock()
        self.actor.iam_conn = iam_mock

        self.actor.create_entity = iam_mock.create_instance_profile
        self.actor.delete_entity = iam_mock.delete_instance_profile
        self.actor.get_all_entities = iam_mock.list_instance_profiles

    @testing.gen_test
    def test_add_role(self):
        yield self.actor._add_role('test', 'testrole')
        self.actor.iam_conn.add_role_to_instance_profile.assert_has_calls(
            [mock.call('test', 'testrole')])

    @testing.gen_test
    def test_add_role_409(self):
        add_role = self.actor.iam_conn.add_role_to_instance_profile
        add_role.side_effect = BotoServerError(409, 'Not there man!')
        yield self.actor._add_role('test', 'testrole')
        self.actor.iam_conn.add_role_to_instance_profile.assert_has_calls(
            [mock.call('test', 'testrole')])

    @testing.gen_test
    def test_add_role_500(self):
        add_role = self.actor.iam_conn.add_role_to_instance_profile
        add_role.side_effect = BotoServerError(500, 'Yikes')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._add_role('test', 'testrole')

    @testing.gen_test
    def test_add_role_dry(self):
        self.actor._dry = True
        yield self.actor._add_role('test', 'testrole')
        self.assertFalse(
            self.actor.iam_conn.add_role_to_instance_profile.called)

    @testing.gen_test
    def test_remove_role(self):
        yield self.actor._remove_role('test', 'testrole')
        self.actor.iam_conn.remove_role_from_instance_profile.assert_has_calls(
            [mock.call('test', 'testrole')])

    @testing.gen_test
    def test_remove_role_404(self):
        remove_role = self.actor.iam_conn.remove_role_from_instance_profile
        remove_role.side_effect = BotoServerError(404, 'Not there man!')
        yield self.actor._remove_role('test', 'testrole')
        self.assertFalse(
            self.actor.iam_conn.remove_role_to_instance_profile.called)

    @testing.gen_test
    def test_remove_role_500(self):
        remove_role = self.actor.iam_conn.remove_role_from_instance_profile
        remove_role.side_effect = BotoServerError(500, 'Yikes')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._remove_role('test', 'testrole')

    @testing.gen_test
    def test_remove_role_dry(self):
        self.actor._dry = True
        yield self.actor._remove_role('test', 'testrole')
        self.assertFalse(
            self.actor.iam_conn.remove_role_from_instance_profile.called)

    @testing.gen_test
    def test_ensure_role_matching(self):
        fake_profile = {
            'get_instance_profile_response': {
                'get_instance_profile_result': {
                    'instance_profile': {
                        'roles': {
                            'member': {
                                'role_name': 'test-role'
                            }
                        }
                    }
                }
            }
        }
        self.actor.iam_conn.get_instance_profile.return_value = fake_profile
        yield self.actor._ensure_role('test', 'test-role')
        self.actor.iam_conn.get_instance_profile.assert_called_with('test')

    @testing.gen_test
    def test_ensure_role_not_matching(self):
        fake_profile = {
            'get_instance_profile_response': {
                'get_instance_profile_result': {
                    'instance_profile': {
                        'roles': {
                            'member': {
                                'role_name': 'test-role'
                            }
                        }
                    }
                }
            }
        }
        self.actor.iam_conn.get_instance_profile.return_value = fake_profile
        self.actor._add_role = mock.MagicMock()
        self.actor._add_role.side_effect = [tornado_value(None)]
        self.actor._remove_role = mock.MagicMock()
        self.actor._remove_role.side_effect = [tornado_value(None),
                                               tornado_value(None)]

        yield self.actor._ensure_role('test', 'new-test-role')
        self.actor.iam_conn.get_instance_profile.assert_called_with('test')
        self.actor._remove_role.assert_called_with('test', 'test-role')
        self.actor._add_role.assert_called_with('test', 'new-test-role')

        yield self.actor._ensure_role('test', None)
        self.actor.iam_conn.get_instance_profile.assert_called_with('test')
        self.actor._remove_role.assert_called_with('test', 'test-role')

    @testing.gen_test
    def test_ensure_role_matching_404(self):
        self.actor.iam_conn.get_instance_profile.side_effect = BotoServerError(
            404, 'No profile')
        self.actor._add_role = mock.MagicMock()
        self.actor._add_role.side_effect = [tornado_value(None)]

        yield self.actor._ensure_role('test', 'test-role')
        self.actor.iam_conn.get_instance_profile.assert_called_with('test')
        self.actor._add_role.assert_called_with('test', 'test-role')

    @testing.gen_test
    def test_ensure_role_matching_500(self):
        self.actor.iam_conn.get_instance_profile.side_effect = BotoServerError(
            500, 'Error')
        self.actor._add_role = mock.MagicMock()
        self.actor._add_role.side_effect = [tornado_value(None)]

        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._ensure_role('test', 'test-role')
        self.actor.iam_conn.get_instance_profile.assert_called_with('test')

    @testing.gen_test
    def test_ensure_role_matching_key_error(self):
        self.actor.iam_conn.get_instance_profile.side_effect = KeyError('')
        self.actor._add_role = mock.MagicMock()
        self.actor._add_role.side_effect = [tornado_value(None)]

        yield self.actor._ensure_role('test', 'test-role')
        self.actor.iam_conn.get_instance_profile.assert_called_with('test')
        self.actor._add_role.assert_called_with('test', 'test-role')

    @testing.gen_test
    def test_ensure_role_matching_key_error_and_no_role(self):
        self.actor.iam_conn.get_instance_profile.side_effect = KeyError('')
        self.actor._add_role = mock.MagicMock()
        self.actor._add_role.side_effect = [tornado_value(None)]

        yield self.actor._ensure_role('test', None)
        self.actor.iam_conn.get_instance_profile.assert_called_with('test')

    @testing.gen_test
    def test_execute_absent(self):
        self.actor._options['state'] = 'absent'
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)

    @testing.gen_test
    def test_execute(self):
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_role = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        self.actor._ensure_role.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)
        self.assertTrue(self.actor._ensure_role.called)

    @testing.gen_test
    def test_execute_no_role(self):
        self.actor._options['role'] = None
        self.actor._ensure_entity = mock.MagicMock()
        self.actor._ensure_entity.side_effect = [tornado_value(None)]
        self.actor._ensure_role = mock.MagicMock()
        self.actor._ensure_role.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_entity.called)
        self.assertFalse(self.actor._ensure_role.called)
