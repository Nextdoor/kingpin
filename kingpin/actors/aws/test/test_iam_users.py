import logging

from boto.exception import BotoServerError
from tornado import testing
from tornado import gen
import mock

from kingpin.actors import exceptions
from kingpin.actors.aws import settings
from kingpin.actors.aws import iam

log = logging.getLogger(__name__)


@gen.coroutine
def tornado_value(*args):
    """Returns whatever is passed in. Used for testing."""
    raise gen.Return(*args)


class TestUser(testing.AsyncTestCase):

    def setUp(self):
        super(TestUser, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        reload(iam)

        # Create our actor object with some basics... then mock out the IAM
        # connections..
        self.actor = iam.User(
            'Unit Test',
            {'name': 'test',
             'state': 'present'})
        self.actor.iam_conn = mock.Mock()

    @testing.gen_test
    def test_execute(self):
        ensure_mock = mock.MagicMock(name='_ensure_user')
        self.actor._ensure_user = ensure_mock
        self.actor._ensure_user.side_effect = [tornado_value(None)]

        yield self.actor._execute()
        ensure_mock.assert_called_with('test', 'present')

    @testing.gen_test
    def test_get_user(self):
        # Test a random unexpected failure
        self.actor.iam_conn.get_all_users.side_effect = BotoServerError(
            500, 'Yikes!')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._get_user('test')
        self.actor.iam_conn.get_all_users.assert_called_once()
        self.actor.iam_conn.get_all_users.reset_mock()

        # Reset the side effect to None, now we're going to use return_values
        # instead
        self.actor.iam_conn.get_all_users.side_effect = None

        # Create some valid test user objects...
        matching_user = {
            u'path': u'/', u'create_date': u'2016-04-05T22:15:24Z',
            u'user_name': u'test', u'arn':
            u'arn:aws:iam::123123123123:user/test', u'user_id':
            u'AIDAXXCXXXXXXXXXAAC2E'}
        not_matching_user = {
            u'path': u'/', u'create_date': u'2016-04-05T22:15:24Z',
            u'user_name': u'some-other-user', u'arn':
            u'arn:aws:iam::123123123123:user/test', u'user_id':
            u'AIDAXXCXXXXXXXXXAAC2E'}

        # Now, first test ... no 'matching' user in the list
        self.actor.iam_conn.get_all_users.return_value = {
            'list_users_response': {
                'list_users_result': {
                    'users': [not_matching_user, not_matching_user]}}}
        ret = yield self.actor._get_user('test')
        self.actor.iam_conn.get_all_users.assert_called_once()
        self.actor.iam_conn.get_all_users.reset_mock()
        self.assertEquals(ret, None)

        # Next, lets return TOO MANY matching users. This is bad.
        self.actor.iam_conn.get_all_users.return_value = {
            'list_users_response': {
                'list_users_result': {
                    'users': [matching_user, matching_user]}}}
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._get_user('test')
        self.actor.iam_conn.get_all_users.assert_called_once()
        self.actor.iam_conn.get_all_users.reset_mock()

        # Finally, lets return one matching and a non matching user
        self.actor.iam_conn.get_all_users.return_value = {
            'list_users_response': {
                'list_users_result': {
                    'users': [not_matching_user, matching_user]}}}
        ret = yield self.actor._get_user('test')
        self.actor.iam_conn.get_all_users.assert_called_once()
        self.actor.iam_conn.get_all_users.reset_mock()
        self.assertEquals(ret, matching_user)

    @testing.gen_test
    def test_ensure_user(self):
        create_mock = mock.MagicMock(name='_create_user')
        delete_mock = mock.MagicMock(name='_delete_user')
        get_mock = mock.MagicMock(name='_get_user')
        self.actor._create_user = create_mock
        self.actor._delete_user = delete_mock
        self.actor._get_user = get_mock
        self.actor._create_user.side_effect = [tornado_value(None)]
        self.actor._delete_user.side_effect = [tornado_value(None)]
        self.actor._get_user.side_effect = [tornado_value(None)]

        # Mock out that the user doesn't exist, and we're creating it
        self.actor._get_user.side_effect = [tornado_value(None)]
        yield self.actor._ensure_user('test', 'present')
        create_mock.assert_called_with('test')
        delete_mock.assert_not_called()
        create_mock.reset_mock()
        delete_mock.reset_mock()

        # Pretend like the user already exists..
        user = {
            'get_user_response': {
                'get_user_result': {'user': {'arn': 'fake_arn'}}
            }
        }
        self.actor._get_user.side_effect = [tornado_value(user)]

        # Now if we ask to create the user, make sure we don't make those calls
        # since the user already exists
        self.actor._get_user.side_effect = [tornado_value(user)]
        yield self.actor._ensure_user('test', 'present')
        create_mock.assert_not_called()
        delete_mock.assert_not_called()
        create_mock.reset_mock()
        delete_mock.reset_mock()

        # Since the user is there, lets test deleting them.. do they get
        # deleted?
        self.actor._get_user.side_effect = [tornado_value(user)]
        yield self.actor._ensure_user('test', 'absent')
        create_mock.assert_not_called()
        delete_mock.assert_called_with('test')
        create_mock.reset_mock()
        delete_mock.reset_mock()

        # If the user doesn't exist, make sure we don't try to delete them
        self.actor._get_user.side_effect = [tornado_value(None)]
        yield self.actor._ensure_user('test', 'absent')
        create_mock.assert_not_called()
        delete_mock.assert_not_called()
        create_mock.reset_mock()
        delete_mock.reset_mock()

    @testing.gen_test
    def test_delete_user(self):
        # Pretend it worked...
        self.actor.iam_conn.delete_user.return_value = None
        yield self.actor._delete_user('test')
        self.actor.iam_conn.delete_user.assert_called_with('test')

    @testing.gen_test
    def test_delete_user_already_deleted(self):
        # Exception raised? Handle it!
        self.actor.iam_conn.delete_user.side_effect = BotoServerError(
            404, 'User already gone!')
        yield self.actor._delete_user('test')
        self.actor.iam_conn.delete_user.assert_called_with('test')

    @testing.gen_test
    def test_delete_user_other_exception(self):
        # Exception raised? Handle it!
        self.actor.iam_conn.delete_user.side_effect = BotoServerError(
            500, 'Yikes!')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._delete_user('test')

    @testing.gen_test
    def test_delete_user_dry(self):
        # Make sure we did not call the delete function!
        self.actor._dry = True
        self.actor.iam_conn.delete_user.return_value = None
        yield self.actor._delete_user('test')
        self.actor.iam_conn.delete_user.assert_not_called()

    @testing.gen_test
    def test_create_user(self):
        # Pretend it worked...
        user = {
            'create_user_response': {
                'create_user_result': {'user': {'arn': 'fake_arn'}}
            }
        }
        self.actor.iam_conn.create_user.return_value = user
        yield self.actor._create_user('test')
        self.actor.iam_conn.create_user.assert_called_with('test')

    @testing.gen_test
    def test_create_user_already_exists(self):
        self.actor.iam_conn.create_user.side_effect = BotoServerError(
            409, 'User already exists')
        yield self.actor._create_user('test')
        self.actor.iam_conn.create_user.assert_called_with('test')

    @testing.gen_test
    def test_create_user_other_exception(self):
        self.actor.iam_conn.create_user.side_effect = BotoServerError(
            500, 'Yikes!')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._create_user('test')

    @testing.gen_test
    def test_create_user_dry(self):
        # Make sure we did not call the create function!
        self.actor._dry = True
        yield self.actor._create_user('test')
        self.actor.iam_conn.create_user.assert_not_called()
