import logging

from boto.exception import S3ResponseError
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
            })
        self.actor.s3_conn = mock.MagicMock()

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
        self.actor._delete_bucket = mock.MagicMock()
        self.actor._delete_bucket.side_effect = [tornado_value(None)]

        ret = yield self.actor._ensure_bucket()
        self.assertEquals(None, ret)
        self.assertFalse(self.actor._create_bucket.called)
        self.actor._delete_bucket.assert_called_with(True)

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
    def test_delete_bucket_dry(self):
        self.actor._dry = True
        fake_bucket = mock.MagicMock()
        fake_bucket.side_effect = [tornado_value(None)]
        fake_bucket.get_all_keys.return_value = []
        yield self.actor._delete_bucket(fake_bucket)
        self.assertTrue(fake_bucket.get_all_keys.called)
        self.assertFalse(fake_bucket.delete.called)

    @testing.gen_test
    def test_delete_bucket_dry_files_exist(self):
        self.actor._dry = True
        fake_bucket = mock.MagicMock()
        fake_bucket.side_effect = [tornado_value(None)]
        fake_bucket.get_all_keys.return_value = [1, 2, 3]
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._delete_bucket(fake_bucket)

    @testing.gen_test
    def test_delete_bucket(self):
        fake_bucket = mock.MagicMock()
        fake_bucket.side_effect = [tornado_value(None)]
        fake_bucket.get_all_keys.return_value = []
        yield self.actor._delete_bucket(fake_bucket)
        self.assertTrue(fake_bucket.get_all_keys.called)
        self.assertTrue(fake_bucket.delete.called)

    @testing.gen_test
    def test_delete_bucket_409(self):
        fake_bucket = mock.MagicMock()
        fake_bucket.side_effect = [tornado_value(None)]
        fake_bucket.get_all_keys.return_value = []
        fake_bucket.delete.side_effect = S3ResponseError(409, 'Files in it!')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._delete_bucket(fake_bucket)

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
    def test_ensure_policy_is_present_and_wants_absent_dry(self):
        self.actor._dry = True
        fake_bucket = mock.MagicMock()
        fake_bucket.get_policy.return_value = '{"fake_pol": 1}'
        self.actor.policy = ''
        yield self.actor._ensure_policy(fake_bucket)

    @testing.gen_test
    def test_ensure_policy_is_present_and_wants_different_dry(self):
        self.actor._dry = True
        fake_bucket = mock.MagicMock()
        fake_bucket.get_policy.return_value = '{"fake_pol": 1}'
        yield self.actor._ensure_policy(fake_bucket)
        self.assertFalse(fake_bucket.set_policy.called)

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
        yield self.actor._execute()
        self.assertTrue(self.actor._ensure_bucket.called)
        self.assertTrue(self.actor._ensure_policy.called)
