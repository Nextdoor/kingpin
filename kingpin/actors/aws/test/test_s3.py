import logging

from boto.exception import S3ResponseError
from boto.s3 import lifecycle
from tornado import testing
import mock

from kingpin.actors import exceptions
from kingpin.actors.aws import base as aws_base
from kingpin.actors.aws import s3 as s3_actor
from kingpin.actors.aws import settings
from kingpin.actors.test.helper import tornado_value

log = logging.getLogger(__name__)


class TestBucket(testing.AsyncTestCase):

    def setUp(self):
        super(TestBucket, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        reload(s3_actor)

        self.actor = s3_actor.Bucket(
            options={
                'name': 'test',
                'region': 'us-east-1',
                'policy': 'examples/aws.s3/amazon_put.json',
                'lifecycle': [{
                    'id': 'test',
                    'prefix': '/test',
                    'status': 'Enabled',
                    'expiration': "30",
                    'transition': {
                        'days': "45",
                        'storage_class': 'GLACIER',
                    }
                }],
                'logging': {
                    'target': 'test_target',
                    'prefix': '/prefix'
                },
                'versioning': False,
            })
        self.actor.s3_conn = mock.MagicMock()

    def test_init_with_bogus_logging_config(self):
        with self.assertRaises(exceptions.InvalidOptions):
            s3_actor.Bucket(
                options={
                    'name': 'test',
                    'logging': {
                        'invalid_data': 'bad_field'
                    }})

    def test_generate_lifecycle_empty_returns_none(self):
        ret = self.actor._generate_lifecycle([])
        self.assertEquals(ret, None)

    def test_generate_lifecycle_missing_expiration(self):
        bad_config = [
            {'id': 'test', 'prefix': '/', 'state': 'Enabled'}
        ]
        with self.assertRaises(s3_actor.InvalidBucketConfig):
            self.actor._generate_lifecycle(bad_config)

    def test_generate_lifecycle_valid_config(self):
        # Validates that the generated config called by the __init__ class is
        # correct based on the actor configuration in the setUp() method above
        self.assertEquals(len(self.actor.lifecycle), 1)

        # Verify that the rule was created with the basic options
        r = self.actor.lifecycle[0]
        self.assertEquals(r.id, 'test')
        self.assertEquals(r.prefix, '/test')
        self.assertEquals(r.status, 'Enabled')

        # Validate that the string "30" was turned into an Expiration object
        self.assertEquals(r.expiration.days, 30)

        # Validate that the transition config was built properly too
        self.assertEquals(r.transition.days, 45)

    @testing.gen_test
    def test_get_bucket_exists(self):
        fake_bucket = mock.MagicMock()
        self.actor.s3_conn.get_bucket.return_value = fake_bucket
        ret = yield self.actor._get_bucket()
        self.assertEquals(fake_bucket, ret)

    @testing.gen_test
    def test_get_bucket_301(self):
        self.actor.s3_conn.get_bucket.side_effect = S3ResponseError(
            301, 'Wrong region buddy')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._get_bucket()

    @testing.gen_test
    def test_get_bucket_404(self):
        self.actor.s3_conn.get_bucket.side_effect = S3ResponseError(
            404, 'Not here')
        ret = yield self.actor._get_bucket()
        self.assertEquals(None, ret)

    @testing.gen_test
    def test_get_bucket_500(self):
        self.actor.s3_conn.get_bucket.side_effect = S3ResponseError(
            500, 'Something else happened')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._get_bucket()

    @testing.gen_test
    def test_ensure_bucket_is_present_and_wants_present(self):
        self.actor._options['state'] = 'present'
        self.actor._get_bucket = mock.MagicMock()
        self.actor._get_bucket.side_effect = [tornado_value(True)]
        self.actor._create_bucket = mock.MagicMock()
        self.actor._create_bucket.side_effect = [tornado_value(None)]
        self.actor._delete_bucket = mock.MagicMock()
        self.actor._delete_bucket.side_effect = [tornado_value(None)]

        ret = yield self.actor._ensure_bucket()
        self.assertEquals(True, ret)
        self.assertFalse(self.actor._create_bucket.called)
        self.assertFalse(self.actor._delete_bucket.called)

    @testing.gen_test
    def test_ensure_bucket_is_present_and_wants_absent(self):
        self.actor._options['state'] = 'absent'
        self.actor._get_bucket = mock.MagicMock()
        self.actor._get_bucket.side_effect = [tornado_value(True)]
        self.actor._create_bucket = mock.MagicMock()
        self.actor._create_bucket.side_effect = [tornado_value(None)]
        self.actor._verify_can_delete_bucket = mock.MagicMock()
        self.actor._verify_can_delete_bucket.side_effect = [
            tornado_value(None)]
        self.actor._delete_bucket = mock.MagicMock()
        self.actor._delete_bucket.side_effect = [tornado_value(None)]

        ret = yield self.actor._ensure_bucket()
        self.assertEquals(None, ret)
        self.assertFalse(self.actor._create_bucket.called)
        self.actor._verify_can_delete_bucket.assert_called_with(bucket=True)
        self.actor._delete_bucket.assert_called_with(bucket=True)

    @testing.gen_test
    def test_ensure_bucket_is_absent_and_wants_present(self):
        self.actor._options['state'] = 'present'
        self.actor._get_bucket = mock.MagicMock()
        self.actor._get_bucket.side_effect = [tornado_value(None)]
        self.actor._create_bucket = mock.MagicMock()
        self.actor._create_bucket.side_effect = [tornado_value(True)]
        self.actor._delete_bucket = mock.MagicMock()
        self.actor._delete_bucket.side_effect = [tornado_value(None)]

        ret = yield self.actor._ensure_bucket()
        self.assertEquals(True, ret)
        self.assertTrue(self.actor._create_bucket.called)
        self.assertFalse(self.actor._delete_bucket.called)

    @testing.gen_test
    def test_ensure_bucket_is_absent_and_wants_absent(self):
        self.actor._options['state'] = 'absent'
        self.actor._get_bucket = mock.MagicMock()
        self.actor._get_bucket.side_effect = [tornado_value(None)]
        self.actor._create_bucket = mock.MagicMock()
        self.actor._create_bucket.side_effect = [tornado_value(None)]
        self.actor._delete_bucket = mock.MagicMock()
        self.actor._delete_bucket.side_effect = [tornado_value(None)]

        ret = yield self.actor._ensure_bucket()
        self.assertEquals(None, ret)
        self.assertFalse(self.actor._create_bucket.called)
        self.assertFalse(self.actor._delete_bucket.called)

    @testing.gen_test
    def test_create_bucket_dry(self):
        self.actor._dry = True
        self.actor.s3_conn.create_bucket = mock.MagicMock()
        self.actor.s3_conn.create_bucket.return_value = True
        ret = yield self.actor._create_bucket()
        self.assertTrue(isinstance(ret, mock.MagicMock))
        self.assertFalse(self.actor.s3_conn.create_bucket.called)

    @testing.gen_test
    def test_create_bucket(self):
        self.actor.s3_conn.create_bucket = mock.MagicMock()
        self.actor.s3_conn.create_bucket.return_value = True
        ret = yield self.actor._create_bucket()
        self.assertEquals(True, ret)
        self.actor.s3_conn.create_bucket.assert_called_with('test')

    @testing.gen_test
    def test_verify_can_delete_bucket(self):
        fake_bucket = mock.MagicMock()
        fake_bucket.get_all_keys.return_value = [1, 2, 3]
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._verify_can_delete_bucket(fake_bucket)

    @testing.gen_test
    def test_delete_bucket(self):
        fake_bucket = mock.MagicMock()
        fake_bucket.side_effect = [tornado_value(None)]
        yield self.actor._delete_bucket(bucket=fake_bucket)
        self.assertTrue(fake_bucket.delete.called)

    @testing.gen_test
    def test_delete_bucket_409(self):
        fake_bucket = mock.MagicMock()
        fake_bucket.side_effect = [tornado_value(None)]
        fake_bucket.delete.side_effect = S3ResponseError(409, 'Files in it!')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._delete_bucket(bucket=fake_bucket)

    @testing.gen_test
    def test_ensure_policy_is_500(self):
        fake_bucket = mock.MagicMock()
        fake_bucket.get_policy.side_effect = S3ResponseError(500, 'None')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._ensure_policy(fake_bucket)

    @testing.gen_test
    def test_ensure_policy_is_404_and_wants_absent(self):
        fake_bucket = mock.MagicMock()
        fake_bucket.get_policy.side_effect = S3ResponseError(404, 'None')
        self.actor.policy = ''
        yield self.actor._ensure_policy(fake_bucket)

    @testing.gen_test
    def test_ensure_policy_is_present_and_wants_absent(self):
        fake_bucket = mock.MagicMock()
        fake_bucket.get_policy.return_value = '{"fake_pol": 1}'
        self.actor.policy = ''
        yield self.actor._ensure_policy(fake_bucket)
        self.assertTrue(fake_bucket.delete_policy.called)

    @testing.gen_test
    def test_ensure_policy_is_present_and_wants_absent_500(self):
        fake_bucket = mock.MagicMock()
        fake_bucket.get_policy.return_value = '{"fake_pol": 1}'
        fake_bucket.delete_policy.side_effect = S3ResponseError(500, 'None')
        self.actor.policy = ''
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._ensure_policy(fake_bucket)

    @testing.gen_test
    def test_ensure_policy_is_present_and_wants_same(self):
        fake_bucket = mock.MagicMock()
        fake_bucket.get_policy.return_value = '{"fake_pol": 1}'
        self.actor.policy = {"fake_pol": 1}
        yield self.actor._ensure_policy(fake_bucket)
        self.assertFalse(fake_bucket.set_policy.called)

    @testing.gen_test
    def test_ensure_policy_is_present_and_wants_different(self):
        fake_bucket = mock.MagicMock()
        fake_bucket.get_policy.return_value = '{"fake_pol": 1}'
        yield self.actor._ensure_policy(fake_bucket)
        self.assertTrue(fake_bucket.set_policy.called)

    @testing.gen_test
    def test_ensure_policy_is_present_and_wants_different_malformed(self):
        malformed_exc = S3ResponseError(400, 'Bad')
        malformed_exc.error_code = 'MalformedPolicy'
        fake_bucket = mock.MagicMock()
        fake_bucket.get_policy.return_value = '{"fake_pol": 1}'
        fake_bucket.set_policy.side_effect = malformed_exc
        with self.assertRaises(aws_base.InvalidPolicy):
            yield self.actor._ensure_policy(fake_bucket)

    @testing.gen_test
    def test_ensure_policy_is_present_and_wants_different_500(self):
        fake_bucket = mock.MagicMock()
        fake_bucket.get_policy.return_value = '{"fake_pol": 1}'
        fake_bucket.set_policy.side_effect = S3ResponseError(500, 'Fail')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._ensure_policy(fake_bucket)

    @testing.gen_test
    def test_ensure_logging_is_present_and_wants_absent(self):
        self.actor._options['logging'] = {'target': ''}
        fake_logging_status = mock.MagicMock()
        fake_logging_status.target = 'some_bucket'
        fake_logging_status.prefix = None
        fake_bucket = mock.MagicMock()
        fake_bucket.get_logging_status.return_value = fake_logging_status
        yield self.actor._ensure_logging(fake_bucket)
        self.assertTrue(fake_bucket.get_logging_status.called)
        self.assertTrue(fake_bucket.disable_logging.called)
        self.assertFalse(fake_bucket.enable_logging.called)

    @testing.gen_test
    def test_ensure_logging_is_absent_and_wants_absent(self):
        self.actor._options['logging'] = {'target': ''}
        fake_logging_status = mock.MagicMock()
        fake_logging_status.target = None
        fake_logging_status.prefix = None
        fake_bucket = mock.MagicMock()
        fake_bucket.get_logging_status.return_value = fake_logging_status
        yield self.actor._ensure_logging(fake_bucket)
        self.assertTrue(fake_bucket.get_logging_status.called)
        self.assertFalse(fake_bucket.disable_logging.called)
        self.assertFalse(fake_bucket.enable_logging.called)

    @testing.gen_test
    def test_ensure_logging_is_absent_and_wants_present(self):
        fake_logging_status = mock.MagicMock()
        fake_logging_status.target = None
        fake_logging_status.prefix = None
        fake_bucket = mock.MagicMock()
        fake_bucket.get_logging_status.return_value = fake_logging_status
        yield self.actor._ensure_logging(fake_bucket)
        self.assertTrue(fake_bucket.get_logging_status.called)
        self.assertFalse(fake_bucket.disable_logging.called)
        fake_bucket.enable_logging.assert_has_calls(
            [mock.call('test_target', '/prefix')])

    @testing.gen_test
    def test_ensure_logging_is_present_and_matches(self):
        fake_logging_status = mock.MagicMock()
        fake_logging_status.target = 'test_target'
        fake_logging_status.prefix = '/prefix'
        fake_bucket = mock.MagicMock()
        fake_bucket.get_logging_status.return_value = fake_logging_status
        yield self.actor._ensure_logging(fake_bucket)
        self.assertTrue(fake_bucket.get_logging_status.called)
        self.assertFalse(fake_bucket.disable_logging.called)
        self.assertFalse(fake_bucket.enable_logging.called)

    @testing.gen_test
    def test_ensure_logging_is_absent_and_wants_present_400(self):
        fake_logging_status = mock.MagicMock()
        fake_logging_status.target = 'some_new_target'
        fake_logging_status.prefix = '/prefix'
        fake_bucket = mock.MagicMock()
        fake_bucket.get_logging_status.return_value = fake_logging_status
        invalid_target_exc = S3ResponseError(500, 'Damn')
        invalid_target_exc.error_code = 'InvalidTargetBucketForLogging'
        fake_bucket.enable_logging.side_effect = invalid_target_exc
        with self.assertRaises(s3_actor.InvalidBucketConfig):
            yield self.actor._ensure_logging(fake_bucket)

    @testing.gen_test
    def test_ensure_logging_is_absent_and_wants_present_500(self):
        fake_logging_status = mock.MagicMock()
        fake_logging_status.target = 'some_new_target'
        fake_logging_status.prefix = '/prefix'
        fake_bucket = mock.MagicMock()
        fake_bucket.get_logging_status.return_value = fake_logging_status
        fake_bucket.enable_logging.side_effect = S3ResponseError(500, 'Damn')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._ensure_logging(fake_bucket)

    @testing.gen_test
    def test_ensure_versioning_is_absent_and_wants_disabled(self):
        self.actor._options['versioning'] = False
        versioning = {}
        fake_bucket = mock.MagicMock()
        fake_bucket.get_versioning_status.return_value = versioning
        yield self.actor._ensure_versioning(fake_bucket)
        self.assertFalse(fake_bucket.configure_versioning.called)

    @testing.gen_test
    def test_ensure_versioning_is_suspended_and_wants_enabled(self):
        self.actor._options['versioning'] = False
        versioning = {'MfaDelete': 'Disabled', 'Versioning': 'Suspended'}
        fake_bucket = mock.MagicMock()
        fake_bucket.get_versioning_status.return_value = versioning
        yield self.actor._ensure_versioning(fake_bucket)
        self.assertFalse(fake_bucket.configure_versioning.called)

    @testing.gen_test
    def test_ensure_versioning_is_enabled_and_wants_suspended(self):
        self.actor._options['versioning'] = False
        versioning = {'MfaDelete': 'Disabled', 'Versioning': 'Enabled'}
        fake_bucket = mock.MagicMock()
        fake_bucket.get_versioning_status.return_value = versioning
        yield self.actor._ensure_versioning(fake_bucket)
        self.assertTrue(fake_bucket.configure_versioning.called)

    @testing.gen_test
    def test_ensure_versioning_is_enabled_and_wants_enabled(self):
        self.actor._options['versioning'] = True
        versioning = {'MfaDelete': 'Disabled', 'Versioning': 'Enabled'}
        fake_bucket = mock.MagicMock()
        fake_bucket.get_versioning_status.return_value = versioning
        yield self.actor._ensure_versioning(fake_bucket)
        self.assertFalse(fake_bucket.configure_versioning.called)

    @testing.gen_test
    def test_ensure_versioning_is_absent_and_wants_enabled(self):
        self.actor._options['versioning'] = True
        versioning = {}
        fake_bucket = mock.MagicMock()
        fake_bucket.get_versioning_status.return_value = versioning
        yield self.actor._ensure_versioning(fake_bucket)
        self.assertTrue(fake_bucket.configure_versioning.called)

    @testing.gen_test
    def test_ensure_lifecycle_raises_exc(self):
        self.actor.lifecycle = None
        fake_bucket = mock.MagicMock()
        exc = S3ResponseError(500, 'Empty')
        fake_bucket.get_lifecycle_config.side_effect = exc
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._ensure_lifecycle(fake_bucket)

    @testing.gen_test
    def test_ensure_lifecycle_is_absent_and_wants_absent(self):
        self.actor.lifecycle = None
        fake_bucket = mock.MagicMock()
        exc = S3ResponseError(404, 'Empty')
        fake_bucket.get_lifecycle_config.side_effect = exc
        yield self.actor._ensure_lifecycle(fake_bucket)
        self.assertFalse(fake_bucket.configure_lifecycle.called)
        self.assertFalse(fake_bucket.delete_lifecycle_configuration.called)

    @testing.gen_test
    def test_ensure_lifecycle_is_present_and_wants_absent(self):
        self.actor.lifecycle = None
        fake_bucket = mock.MagicMock()
        fake_bucket.get_lifecycle_config.return_value = lifecycle.Lifecycle()
        yield self.actor._ensure_lifecycle(fake_bucket)
        self.assertFalse(fake_bucket.configure_lifecycle.called)
        self.assertTrue(fake_bucket.delete_lifecycle_configuration.called)

    @testing.gen_test
    def test_ensure_lifecycle_is_absent_and_wants_present(self):
        fake_bucket = mock.MagicMock()
        exc = S3ResponseError(404, 'Empty')
        fake_bucket.get_lifecycle_config.side_effect = exc
        yield self.actor._ensure_lifecycle(fake_bucket)
        self.assertTrue(fake_bucket.configure_lifecycle.called)
        self.assertFalse(fake_bucket.delete_lifecycle_configuration.called)

    @testing.gen_test
    def test_ensure_lifecycle_is_present_and_wants_different(self):
        fake_bucket = mock.MagicMock()
        fake_bucket.get_lifecycle_config.return_value = lifecycle.Lifecycle()
        yield self.actor._ensure_lifecycle(fake_bucket)
        self.assertTrue(fake_bucket.configure_lifecycle.called)
        self.assertFalse(fake_bucket.delete_lifecycle_configuration.called)

    @testing.gen_test
    def test_delete_lifecycle(self):
        fake_bucket = mock.MagicMock()
        yield self.actor._delete_lifecycle(fake_bucket)
        self.assertTrue(fake_bucket.delete_lifecycle_configuration.called)

    @testing.gen_test
    def test_configure_lifecycle(self):
        fake_bucket = mock.MagicMock()
        yield self.actor._configure_lifecycle(bucket=fake_bucket,
                                              lifecycle=self.actor.lifecycle)
        self.assertTrue(fake_bucket.configure_lifecycle.called)

    @testing.gen_test
    def test_configure_lifecycle_raises_exc(self):
        fake_bucket = mock.MagicMock()
        fake_bucket.configure_lifecycle.side_effect = S3ResponseError(
            400, 'bad config')
        with self.assertRaises(s3_actor.InvalidBucketConfig):
            yield self.actor._configure_lifecycle(
                bucket=fake_bucket, lifecycle=self.actor.lifecycle)

    @testing.gen_test
    def test_execute_absent(self):
        self.actor._options['state'] = 'absent'
        self.actor._ensure_bucket = mock.MagicMock()
        self.actor._ensure_bucket.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_bucket.called)

    @testing.gen_test
    def test_execute_present(self):
        self.actor._ensure_bucket = mock.MagicMock()
        self.actor._ensure_bucket.side_effect = [tornado_value(None)]
        self.actor._ensure_policy = mock.MagicMock()
        self.actor._ensure_policy.side_effect = [tornado_value(None)]
        self.actor._ensure_logging = mock.MagicMock()
        self.actor._ensure_logging.side_effect = [tornado_value(None)]
        self.actor._ensure_versioning = mock.MagicMock()
        self.actor._ensure_versioning.side_effect = [tornado_value(None)]
        self.actor._ensure_lifecycle = mock.MagicMock()
        self.actor._ensure_lifecycle.side_effect = [tornado_value(None)]
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_bucket.called)
        self.assertTrue(self.actor._ensure_policy.called)
        self.assertTrue(self.actor._ensure_logging.called)
        self.assertTrue(self.actor._ensure_versioning.called)
