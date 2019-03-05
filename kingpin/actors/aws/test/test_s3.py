import logging

from botocore.exceptions import ClientError
from tornado import testing
import mock

from kingpin.actors import exceptions
from kingpin.actors.aws import s3 as s3_actor
from kingpin.actors.aws import settings
import importlib

log = logging.getLogger(__name__)


class TestBucket(testing.AsyncTestCase):

    def setUp(self):
        super(TestBucket, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        importlib.reload(s3_actor)

        self.actor = s3_actor.Bucket(
            options={
                'name': 'test',
                'region': 'us-east-1',
                'policy': 'examples/aws.s3/amazon_put.json',
                'lifecycle': [{
                    'id': 'test',
                    'prefix': '/test',
                    'status': 'Enabled',
                    'transition': {
                        'days': 45,
                        'storage_class': 'GLACIER',
                    },
                    'noncurrent_version_transition': {
                        'noncurrent_days': 14,
                        'storage_class': 'GLACIER',
                    },
                    'expiration': '30'
                }],
                'logging': {
                    'target': 'test_target',
                    'prefix': '/prefix'
                },
                'public_access_block_configuration': {
                    'block_public_acls': True,
                    'block_public_policy': True,
                    'ignore_public_acls': True,
                    'restrict_public_buckets': True,
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

    def test_generate_lifecycle_valid_config(self):
        # Validates that the generated config called by the __init__ class is
        # correct based on the actor configuration in the setUp() method above
        self.assertEqual(len(self.actor.lifecycle), 1)

        # Verify that the rule was created with the basic options
        r = self.actor.lifecycle[0]
        self.assertEqual(r['ID'], 'test')
        self.assertEqual(r['Filter']['Prefix'], '/test')
        self.assertEqual(r['Status'], 'Enabled')

        # Validate that the string "30" was turned into an Expiration object
        self.assertEqual(r['Expiration']['Days'], 30)

        # Validate that the transition config was built properly too
        self.assertEqual(r['Transitions'][0]['Days'], 45)

        # Validate that the transition config was built properly too
        self.assertEqual(
            r['NoncurrentVersionTransitions'][0]['NoncurrentDays'], 14)

    def test_snake_to_camel(self):
        snake = {
            'i_should_be_taller': {
                'me_too_man': [
                    'not_me'
                ]
            }
        }

        self.assertEqual(
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
        self.assertEqual('absent', ret)

    @testing.gen_test
    def test_get_state_present(self):
        self.actor._bucket_exists = True
        ret = yield self.actor._get_state()
        self.assertEqual('present', ret)

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
            {'Error': {'Code': ''}}, 'Error')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._delete_bucket()

    @testing.gen_test
    def test_get_policy(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_policy.return_value = {'Policy': '{}'}
        ret = yield self.actor._get_policy()
        self.assertEqual({}, ret)

    @testing.gen_test
    def test_get_policy_no_bucket(self):
        self.actor._bucket_exists = False
        ret = yield self.actor._get_policy()
        self.assertEqual(ret, None)

    @testing.gen_test
    def test_get_policy_empty(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_policy.side_effect = ClientError(
            {'Error': {'Code': ''}}, 'NoSuchBucketPolicy')
        ret = yield self.actor._get_policy()
        self.assertEqual('', ret)

    @testing.gen_test
    def test_get_policy_exc(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_policy.side_effect = ClientError(
            {'Error': {'Code': ''}}, 'SomeOtherError')
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
            {'Error': {'Code': ''}}, 'MalformedPolicy')
        with self.assertRaises(exceptions.RecoverableActorFailure):
            yield self.actor._set_policy()

        self.actor.s3_conn.put_bucket_policy.assert_has_calls([
            mock.call(Bucket='test', Policy='{}')])

    @testing.gen_test
    def test_set_policy_client_error(self):
        self.actor.policy = {}
        self.actor.s3_conn.put_bucket_policy.side_effect = ClientError(
            {'Error': {'Code': ''}}, 'Some Other Error')
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
        self.assertEqual(
            ret,
            {'target': 'Target-Bucket', 'prefix': 'Target-Prefix'})

    @testing.gen_test
    def test_get_logging_disabled(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_logging.return_value = {}
        ret = yield self.actor._get_logging()
        self.assertEqual(ret, {'target': '', 'prefix': ''})

    @testing.gen_test
    def test_get_logging_no_bucket(self):
        self.actor._bucket_exists = False
        ret = yield self.actor._get_logging()
        self.assertEqual(ret, None)

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
            {'Error': {'Code': ''}}, 'Some error')
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
        self.assertEqual(None, ret)

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
        self.actor.s3_conn.get_bucket_lifecycle_configuration.return_value = {
            'Rules': []}
        ret = yield self.actor._get_lifecycle()
        self.assertEqual(ret, [])

    @testing.gen_test
    def test_get_lifecycle_no_bucket(self):
        self.actor._bucket_exists = False
        ret = yield self.actor._get_lifecycle()
        self.assertEqual(None, ret)

    @testing.gen_test
    def test_get_lifecycle_empty(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_lifecycle_configuration.side_effect = \
            ClientError(
                {'Error': {'Code': ''}}, 'NoSuchLifecycleConfiguration')
        ret = yield self.actor._get_lifecycle()
        self.assertEqual(ret, [])

    @testing.gen_test
    def test_get_lifecycle_clienterror(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_lifecycle_configuration.side_effect = \
            ClientError(
                {'Error': {'Code': ''}}, 'SomeOtherError')
        with self.assertRaises(ClientError):
            yield self.actor._get_lifecycle()

    @testing.gen_test
    def test_compare_lifecycle(self):
        self.actor._bucket_exists = True
        self.actor.lifecycle = [{'test': 'test'}]
        self.actor.s3_conn.get_bucket_lifecycle_configuration.return_value = {
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
        self.actor.s3_conn.get_bucket_lifecycle_configuration.return_value = {
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
        self.actor.s3_conn.put_bucket_lifecycle_configuration.assert_has_calls(
            [
                mock.call(
                    Bucket='test',
                    LifecycleConfiguration={'Rules': [{'test': 'test'}]})
            ]
        )

    @testing.gen_test
    def test_set_lifecycle_client_error(self):
        self.actor.s3_conn.put_bucket_lifecycle_configuration.side_effect = \
            ClientError(
                {'Error': {'Code': ''}}, 'Error')
        with self.assertRaises(s3_actor.InvalidBucketConfig):
            yield self.actor._set_lifecycle()

    @testing.gen_test
    def test_get_public_access_block_configuration(self):
        test_cfg = {
            'BlockPublicAcls': True,
            'BlockPublicPolicy': True,
            'IgnorePublicAcls': True,
            'RestrictPublicBuckets': True
        }

        self.actor._bucket_exists = True
        self.actor.s3_conn.get_public_access_block.return_value = {
            'PublicAccessBlockConfiguration': test_cfg
        }
        ret = yield self.actor._get_public_access_block_configuration()
        self.assertEqual(ret, test_cfg)

    @testing.gen_test
    def test_get_public_access_block_configuration_no_bucket(self):
        self.actor._bucket_exists = False
        ret = yield self.actor._get_public_access_block_configuration()
        self.assertEqual(None, ret)

    @testing.gen_test
    def test_get_public_access_block_configuration_empty(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_public_access_block.side_effect = ClientError(
            {'Error': {}}, 'NoSuchPublicAccessBlockConfiguration')
        ret = yield self.actor._get_public_access_block_configuration()
        self.assertEqual(ret, [])

    @testing.gen_test
    def test_get_public_access_block_configuration_clienterror(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_public_access_block.side_effect = ClientError(
            {'Error': {}}, 'SomeOtherError')
        with self.assertRaises(ClientError):
            yield self.actor._get_public_access_block_configuration()

    @testing.gen_test
    def test_compare_public_access_block_configuration(self):
        self.actor._bucket_exists = True
        self.actor.access_block = [{'test': 'test'}]
        self.actor.s3_conn.get_public_access_block.return_value = {
            'PublicAccessBlockConfiguration': [{'test': 'test'}]}
        ret = yield self.actor._compare_public_access_block_configuration()
        self.assertTrue(ret)

    @testing.gen_test
    def test_compare_public_access_block_configuration_none(self):
        self.actor.access_block = None
        ret = yield self.actor._compare_public_access_block_configuration()
        self.assertTrue(ret)

    @testing.gen_test
    def test_compare_public_access_block_configuration_diff(self):
        self.actor.access_block = [{'test1': 'test'}]
        self.actor.s3_conn.get_public_access_block.return_value = {
            'Rules': [{'test': 'test'}]}
        ret = yield self.actor._compare_public_access_block_configuration()
        self.assertFalse(ret)

    @testing.gen_test
    def test_set_public_access_block_configuration_delete(self):
        self.actor.access_block = {}
        yield self.actor._set_public_access_block_configuration()
        self.actor.s3_conn.delete_public_access_block.assert_has_calls([
            mock.call(Bucket='test')])

    @testing.gen_test
    def test_set_public_access_block_configuration(self):
        self.actor.access_block = {'test': 'test'}
        yield self.actor._set_public_access_block_configuration()
        self.actor.s3_conn.put_public_access_block.assert_has_calls([
            mock.call(
                Bucket='test',
                PublicAccessBlockConfiguration={'test': 'test'})])

    @testing.gen_test
    def test_set_public_access_block_configuration_client_error(self):
        self.actor.s3_conn.put_public_access_block.side_effect = ClientError(
            {'Error': {}}, 'Error')
        with self.assertRaises(s3_actor.InvalidBucketConfig):
            yield self.actor._set_public_access_block_configuration()

    @testing.gen_test
    def test_get_tags(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_tagging.return_value = {
            'TagSet': [{'Key': 'k1', 'Value': 'v1'}]}
        ret = yield self.actor._get_tags()
        self.assertEqual(ret, [{'key': 'k1', 'value': 'v1'}])

    @testing.gen_test
    def test_get_tags_multiple_tags(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_tagging.return_value = {
            'TagSet': [
                {'Key': 'k1', 'Value': 'v1'},
                {'Key': 'k2', 'Value': 'v2'}
            ]}
        ret = yield self.actor._get_tags()
        self.assertEqual(ret, [
            {'key': 'k1', 'value': 'v1'},
            {'key': 'k2', 'value': 'v2'}
        ])

    @testing.gen_test
    def test_get_tags_no_bucket(self):
        self.actor._bucket_exists = False
        ret = yield self.actor._get_tags()
        self.assertEqual(None, ret)

    @testing.gen_test
    def test_get_tags_not_managed(self):
        self.actor._options['tags'] = None
        ret = yield self.actor._get_tags()
        self.assertEqual(None, ret)

    @testing.gen_test
    def test_get_tags_empty(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_tagging.side_effect = ClientError(
            {'Error': {'Code': ''}}, 'NoSuchTagSet')
        ret = yield self.actor._get_tags()
        self.assertEqual(ret, [])

    @testing.gen_test
    def test_get_tags_exc(self):
        self.actor._bucket_exists = True
        self.actor.s3_conn.get_bucket_tagging.side_effect = ClientError(
            {'Error': {'Code': ''}}, 'SomeOtherError')
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
