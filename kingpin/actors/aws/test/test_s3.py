import logging

from botocore.exceptions import ClientError
from tornado import testing
import mock

from kingpin.actors import exceptions
from kingpin.actors.aws import s3 as s3_actor
from kingpin.actors.aws import settings

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
                        'days': 45,
                        'storage_class': 'GLACIER',
                    }
                }],
                'logging': {
                    'target': 'test_target',
                    'prefix': '/prefix'
                },
                'versioning': False,
                'tags': [],
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
        self.assertEquals(r['ID'], 'test')
        self.assertEquals(r['Prefix'], '/test')
        self.assertEquals(r['Status'], 'Enabled')

        # Validate that the string "30" was turned into an Expiration object
        self.assertEquals(r['Expiration']['Days'], 30)

        # Validate that the transition config was built properly too
        self.assertEquals(r['Transition']['Days'], 45)

    def test_snake_to_camel(self):
        snake = {
            'i_should_be_taller': {
                'me_too_man': [
                    'not_me'
                ]
            }
        }

        self.assertEquals(
            self.actor._snake_to_camel(snake),
            {'IShouldBeTaller': {'MeTooMan': ['not_me']}}
        )

    @testing.gen_test
    def test_precache(self):
        self.actor.s3_conn.list_buckets.return_value = {
            'Buckets': [
                {'Name': 'wrong_bucket'},
                {'Name': 'test'}
            ]
        }

        yield self.actor._precache()
        self.assertTrue(self.actor._bucket_exists)

    @testing.gen_test
    def test_get_state_absent(self):
        ret = yield self.actor._get_state()
        self.assertEquals('absent', ret)

    @testing.gen_test
    def test_get_state_present(self):
        self.actor._bucket_exists = True
        ret = yield self.actor._get_state()
        self.assertEquals('present', ret)

    @testing.gen_test
    def test_set_state_absent(self):
        self.actor._options['state'] = 'absent'
        yield self.actor._set_state()
        self.actor.s3_conn.delete_bucket.assert_has_calls([
            mock.call(Bucket='test')])

    @testing.gen_test
    def test_set_state_present(self):
        self.actor._options['state'] = 'present'
        yield self.actor._set_state()
        self.actor.s3_conn.create_bucket.assert_has_calls([
            mock.call(Bucket='test')])

    @testing.gen_test
    def test_create_bucket(self):
        yield self.actor._create_bucket()
        self.actor.s3_conn.create_bucket.assert_called_with(Bucket='test')

    @testing.gen_test
    def test_create_bucket_new_region(self):
        self.actor._options['region'] = 'us-west-1'
        yield self.actor._create_bucket()
        self.actor.s3_conn.create_bucket.assert_called_with(
            Bucket='test',
            CreateBucketConfiguration={'LocationConstraint': 'us-west-1'})

    @testing.gen_test
    def test_verify_can_delete_bucket(self):
        self.actor.s3_conn.list_objects.return_value = {
            'Contents': [1, 2, 3]
        }
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._verify_can_delete_bucket()

    @testing.gen_test
    def test_verify_can_delete_bucket_true(self):
        self.actor.s3_conn.list_objects.return_value = {}
        yield self.actor._verify_can_delete_bucket()

    @testing.gen_test
    def test_delete_bucket(self):
        yield self.actor._delete_bucket()
        self.actor.s3_conn.delete_bucket.assert_has_calls(
            [mock.call(Bucket='test')])

    @testing.gen_test
    def test_delete_bucket_409(self):
        self.actor.s3_conn.delete_bucket.side_effect = ClientError(
            {'Error': {}}, 'Error')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._delete_bucket()

    @testing.gen_test
    def test_get_policy(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_policy.return_value = {'Policy': '{}'}
        ret = yield self.actor._get_policy()
        self.assertEquals({}, ret)

    @testing.gen_test
    def test_get_policy_no_bucket(self):
        self.actor._bucket_exists = False
        ret = yield self.actor._get_policy()
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_get_policy_empty(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_policy.side_effect = ClientError(
            {'Error': {}}, 'NoSuchBucketPolicy')
        ret = yield self.actor._get_policy()
        self.assertEquals('', ret)

    @testing.gen_test
    def test_get_policy_exc(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_policy.side_effect = ClientError(
            {'Error': {}}, 'SomeOtherError')
        with self.assertRaises(ClientError):
            yield self.actor._get_policy()

    @testing.gen_test
    def test_compare_policy(self):
        self.actor._bucket_exists = True
        self.actor.policy = {'test': 'policy'}
        self.actor.s3_conn.get_bucket_policy.return_value = {
            'Policy': '{"test": "policy"}'
        }
        ret = yield self.actor._compare_policy()
        self.assertTrue(ret)

    @testing.gen_test
    def test_compare_policy_false(self):
        self.actor._bucket_exists = True
        self.actor.policy = {'test': 'bah'}
        self.actor.s3_conn.get_bucket_policy.return_value = {
            'Policy': '{"test": "policy"}'
        }
        ret = yield self.actor._compare_policy()
        self.assertFalse(ret)

    @testing.gen_test
    def test_compare_policy_not_managing(self):
        self.actor._bucket_exists = True
        self.actor.policy = None
        self.actor.s3_conn.get_bucket_policy.return_value = {
            'Policy': '{"test": "policy"}'
        }
        ret = yield self.actor._compare_policy()
        self.assertTrue(ret)

    @testing.gen_test
    def test_set_policy(self):
        self.actor.policy = {}
        yield self.actor._set_policy()
        self.actor.s3_conn.put_bucket_policy.assert_has_calls([
            mock.call(Bucket='test', Policy='{}')])

    @testing.gen_test
    def test_set_policy_malformed_policy(self):
        self.actor.policy = {}
        self.actor.s3_conn.put_bucket_policy.side_effect = ClientError(
            {'Error': {}}, 'MalformedPolicy')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._set_policy()

        self.actor.s3_conn.put_bucket_policy.assert_has_calls([
            mock.call(Bucket='test', Policy='{}')])

    @testing.gen_test
    def test_set_policy_client_error(self):
        self.actor.policy = {}
        self.actor.s3_conn.put_bucket_policy.side_effect = ClientError(
            {'Error': {}}, 'Some Other Error')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._set_policy()

        self.actor.s3_conn.put_bucket_policy.assert_has_calls([
            mock.call(Bucket='test', Policy='{}')])

    @testing.gen_test
    def test_set_policy_delete(self):
        self.actor.policy = ''
        yield self.actor._set_policy()
        self.actor.s3_conn.delete_bucket_policy.assert_has_calls([
            mock.call(Bucket='test')])

    @testing.gen_test
    def test_get_logging(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_logging.return_value = {
            'LoggingEnabled': {
                'TargetBucket': 'Target-Bucket',
                'TargetPrefix': 'Target-Prefix'
            }
        }

        ret = yield self.actor._get_logging()
        self.assertEquals(
            ret,
            {'target': 'Target-Bucket', 'prefix': 'Target-Prefix'})

    @testing.gen_test
    def test_get_logging_disabled(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_logging.return_value = {}
        ret = yield self.actor._get_logging()
        self.assertEquals(ret, {'target': '', 'prefix': ''})

    @testing.gen_test
    def test_get_logging_no_bucket(self):
        self.actor._bucket_exists = False
        ret = yield self.actor._get_logging()
        self.assertEquals(ret, None)

    @testing.gen_test
    def test_set_logging_not_desired(self):
        self.actor._options['logging'] = None
        yield self.actor._set_logging()
        self.assertFalse(self.actor.s3_conn.put_bucket_logging.called)

    @testing.gen_test
    def test_set_logging_disabled(self):
        self.actor._options['logging'] = {'target': '', 'prefix': ''}
        yield self.actor._set_logging()
        self.actor.s3_conn.put_bucket_logging.assert_has_calls([
            mock.call(Bucket='test', BucketLoggingStatus={})])

    @testing.gen_test
    def test_set_logging(self):
        self.actor._options['logging'] = {'target': 'tgt', 'prefix': 'pfx'}
        yield self.actor._set_logging()
        self.actor.s3_conn.put_bucket_logging.assert_has_calls([
            mock.call(
                Bucket='test',
                BucketLoggingStatus={'LoggingEnabled': {
                    'TargetPrefix': 'pfx', 'TargetBucket': 'tgt'}}
            )])

    @testing.gen_test
    def test_set_logging_client_error(self):
        self.actor.s3_conn.put_bucket_logging.side_effect = ClientError(
            {'Error': {}}, 'Some error')
        with self.assertRaises(s3_actor.InvalidBucketConfig):
            yield self.actor._set_logging()

    @testing.gen_test
    def test_get_versioning(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_versioning.return_value = {
            'Status': 'Enabled'}
        ret = yield self.actor._get_versioning()
        self.assertTrue(ret)

    @testing.gen_test
    def test_get_versioning_no_bucket(self):
        self.actor._bucket_exists = False
        ret = yield self.actor._get_versioning()
        self.assertEquals(None, ret)

    @testing.gen_test
    def test_get_versioning_suspended(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_versioning.return_value = {
            'Status': 'Suspended'}
        ret = yield self.actor._get_versioning()
        self.assertFalse(ret)

    @testing.gen_test
    def test_set_versioning(self):
        self.actor._options['versioning'] = True
        yield self.actor._set_versioning()
        self.actor.s3_conn.put_bucket_versioning.assert_has_calls([
            mock.call(
                Bucket='test',
                VersioningConfiguration={'Status': 'Enabled'})])

    @testing.gen_test
    def test_set_versioning_suspended(self):
        self.actor._options['versioning'] = False
        yield self.actor._set_versioning()
        self.actor.s3_conn.put_bucket_versioning.assert_has_calls([
            mock.call(
                Bucket='test',
                VersioningConfiguration={'Status': 'Suspended'})])

    @testing.gen_test
    def test_set_versioning_none(self):
        self.actor._options['versioning'] = None
        yield self.actor._set_versioning()
        self.assertFalse(self.actor.s3_conn.put_bucket_versioning.called)

    @testing.gen_test
    def test_get_lifecycle(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_lifecycle.return_value = {
            'Rules': []}
        ret = yield self.actor._get_lifecycle()
        self.assertEquals(ret, [])

    @testing.gen_test
    def test_get_lifecycle_no_bucket(self):
        self.actor._bucket_exists = False
        ret = yield self.actor._get_lifecycle()
        self.assertEquals(None, ret)

    @testing.gen_test
    def test_get_lifecycle_empty(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_lifecycle.side_effect = ClientError(
            {'Error': {}}, 'NoSuchLifecycleConfiguration')
        ret = yield self.actor._get_lifecycle()
        self.assertEquals(ret, [])

    @testing.gen_test
    def test_get_lifecycle_clienterror(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_lifecycle.side_effect = ClientError(
            {'Error': {}}, 'SomeOtherError')
        with self.assertRaises(ClientError):
            yield self.actor._get_lifecycle()

    @testing.gen_test
    def test_compare_lifecycle(self):
        self.actor._bucket_exists = True
        self.actor.lifecycle = [{'test': 'test'}]
        self.actor.s3_conn.get_bucket_lifecycle.return_value = {
            'Rules': [{'test': 'test'}]}
        ret = yield self.actor._compare_lifecycle()
        self.assertTrue(ret)

    @testing.gen_test
    def test_compare_lifecycle_none(self):
        self.actor.lifecycle = None
        ret = yield self.actor._compare_lifecycle()
        self.assertTrue(ret)

    @testing.gen_test
    def test_compare_lifecycle_diff(self):
        self.actor.lifecycle = [{'test1': 'test'}]
        self.actor.s3_conn.get_bucket_lifecycle.return_value = {
            'Rules': [{'test': 'test'}]}
        ret = yield self.actor._compare_lifecycle()
        self.assertFalse(ret)

    @testing.gen_test
    def test_set_lifecycle_delete(self):
        self.actor.lifecycle = []
        yield self.actor._set_lifecycle()
        self.actor.s3_conn.delete_bucket_lifecycle.assert_has_calls([
            mock.call(Bucket='test')])

    @testing.gen_test
    def test_set_lifecycle(self):
        self.actor.lifecycle = [{'test': 'test'}]
        yield self.actor._set_lifecycle()
        self.actor.s3_conn.put_bucket_lifecycle.assert_has_calls([
            mock.call(
                Bucket='test',
                LifecycleConfiguration={'Rules': [{'test': 'test'}]})])

    @testing.gen_test
    def test_set_lifecycle_client_error(self):
        self.actor.s3_conn.put_bucket_lifecycle.side_effect = ClientError(
            {'Error': {}}, 'Error')
        with self.assertRaises(s3_actor.InvalidBucketConfig):
            yield self.actor._set_lifecycle()

    @testing.gen_test
    def test_get_tags(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_tagging.return_value = {
            'TagSet': [{'Key': 'k1', 'Value': 'v1'}]}
        ret = yield self.actor._get_tags()
        self.assertEquals(ret, [{'key': 'k1', 'value': 'v1'}])

    @testing.gen_test
    def test_get_tags_multiple_tags(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_tagging.return_value = {
            'TagSet': [
                {'Key': 'k1', 'Value': 'v1'},
                {'Key': 'k2', 'Value': 'v2'}
            ]}
        ret = yield self.actor._get_tags()
        self.assertEquals(ret, [
            {'key': 'k1', 'value': 'v1'},
            {'key': 'k2', 'value': 'v2'}
        ])

    @testing.gen_test
    def test_get_tags_no_bucket(self):
        self.actor._bucket_exists = False
        ret = yield self.actor._get_tags()
        self.assertEquals(None, ret)

    @testing.gen_test
    def test_get_tags_not_managed(self):
        self.actor._options['tags'] = None
        ret = yield self.actor._get_tags()
        self.assertEquals(None, ret)

    @testing.gen_test
    def test_get_tags_empty(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_tagging.side_effect = ClientError(
            {'Error': {}}, 'NoSuchTagSet')
        ret = yield self.actor._get_tags()
        self.assertEquals(ret, [])

    @testing.gen_test
    def test_get_tags_exc(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_tagging.side_effect = ClientError(
            {'Error': {}}, 'SomeOtherError')
        with self.assertRaises(ClientError):
            yield self.actor._get_tags()

    @testing.gen_test
    def test_compare_tags(self):
        self.actor._bucket_exists = True
        self.actor._options['tags'] = [
            {'key': 'test_key', 'value': 'test_value'}
        ]
        self.actor.s3_conn.get_bucket_tagging.return_value = {
            'TagSet': [
                {'Key': 'test_key', 'Value': 'test_value'},
            ]}
        ret = yield self.actor._compare_tags()
        self.assertTrue(ret)

    @testing.gen_test
    def test_compare_tags_false(self):
        self.actor._bucket_exists = True
        self.actor._options['tags'] = [
            {'key': 'test_key', 'value': 'test_value'}
        ]
        self.actor.s3_conn.get_bucket_tagging.return_value = {
            'TagSet': [
                {'Key': 'k1', 'Value': 'v1'},
                {'Key': 'k2', 'Value': 'v2'}
            ]}
        ret = yield self.actor._compare_tags()
        self.assertFalse(ret)

    @testing.gen_test
    def test_compare_tags_not_managing(self):
        self.actor._bucket_exists = True
        self.actor._options['tags'] = None
        ret = yield self.actor._compare_tags()
        self.assertTrue(ret)

    @testing.gen_test
    def test_set_tags_none(self):
        self.actor._options['tags'] = None
        yield self.actor._set_tags()
        self.assertFalse(self.actor.s3_conn.put_bucket_tagging.called)

    @testing.gen_test
    def test_set_tags(self):
        self.actor._options['tags'] = [
            {'key': 'tag1', 'value': 'v1'}
        ]
        yield self.actor._set_tags()
        self.actor.s3_conn.put_bucket_tagging.assert_has_calls([
            mock.call(
                Bucket='test',
                Tagging={'TagSet': [
                    {'Key': 'tag1', 'Value': 'v1'}
                ]})])
