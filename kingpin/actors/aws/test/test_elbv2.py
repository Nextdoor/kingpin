import logging

from tornado import testing
import mock
import botocore.exceptions

from kingpin.actors import exceptions
from kingpin.actors.aws import elbv2 as elbv2_actor
from kingpin.actors.aws import settings
from kingpin.actors.test import helper
import importlib

log = logging.getLogger(__name__)


class TestRegisterInstance(testing.AsyncTestCase):

    def setUp(self):
        super(TestRegisterInstance, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        importlib.reload(elbv2_actor)

    @testing.gen_test
    def test_add(self):
        actor = elbv2_actor.RegisterInstance('UTA', {
            'target_group': 'test',
            'region': 'us-east-1',
            'instances': 'test'})
        actor.elbv2_conn = mock.Mock()
        actor.elbv2_conn.register_targets.return_value = {}

        yield actor._add('target_group_arn', ['i-un173s7'])

        actor.elbv2_conn.register_targets.assert_called_with(
            TargetGroupArn='target_group_arn',
            Targets=[{'Id': 'i-un173s7'}])

    @testing.gen_test
    def test_add_exception(self):
        actor = elbv2_actor.RegisterInstance('UTA', {
            'target_group': 'test',
            'region': 'us-east-1',
            'instances': 'test'})
        actor.elbv2_conn = mock.Mock()
        exc = botocore.exceptions.ClientError({'Error': {'Code': ''}}, 'Test')
        actor.elbv2_conn.register_targets.side_effect = exc

        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            yield actor._add('target_group_arn', ['i-un173s7'])

    @testing.gen_test
    def test_execute(self):
        actor = elbv2_actor.RegisterInstance('UTA', {
            'target_group': 'test',
            'region': 'us-east-1',
            'instances': 'i-test'})

        actor._find_target_group = mock.Mock()
        actor._find_target_group.return_value = helper.tornado_value('arn')
        actor._add = mock.Mock()
        actor._add.return_value = helper.tornado_value(mock.Mock())
        yield actor._execute()
        actor._add.assert_called_with('arn', ['i-test'])

    @testing.gen_test
    def test_execute_self(self):
        # No instance id specified
        actor = elbv2_actor.RegisterInstance('UTA', {
            'target_group': 'test',
            'region': 'us-east-1'})

        actor._find_target_group = mock.Mock()
        actor._find_target_group.return_value = helper.tornado_value('arn')
        actor._add = mock.Mock()
        actor._get_meta_data = helper.mock_tornado('i-test')
        actor._add.return_value = helper.tornado_value(mock.Mock())
        yield actor._execute()
        actor._add.assert_called_with('arn', ['i-test'])


class TestDeregisterInstance(testing.AsyncTestCase):

    def setUp(self):
        super(TestDeregisterInstance, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        settings.RETRYING_SETTINGS = {'stop_max_attempt_number': 1}
        importlib.reload(elbv2_actor)

    @testing.gen_test
    def test_remove(self):
        actor = elbv2_actor.DeregisterInstance('UTA', {
            'target_group': 'test',
            'region': 'us-east-1',
            'instances': 'test'})
        actor.elbv2_conn = mock.Mock()
        actor.elbv2_conn.deregister_targets.return_value = {}

        yield actor._remove('target_group_arn', ['i-un173s7'])

        actor.elbv2_conn.deregister_targets.assert_called_with(
            TargetGroupArn='target_group_arn',
            Targets=[{'Id': 'i-un173s7'}])

    @testing.gen_test
    def test_remove_exception(self):
        actor = elbv2_actor.DeregisterInstance('UTA', {
            'target_group': 'test',
            'region': 'us-east-1',
            'instances': 'test'})
        actor.elbv2_conn = mock.Mock()
        exc = botocore.exceptions.ClientError({'Error': {'Code': ''}}, 'Test')
        actor.elbv2_conn.deregister_targets.side_effect = exc

        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            yield actor._remove('target_group_arn', ['i-un173s7'])

    @testing.gen_test
    def test_execute(self):
        actor = elbv2_actor.DeregisterInstance('UTA', {
            'target_group': 'elb-test',
            'region': 'us-east-1',
            'instances': 'i-test'})

        actor._find_target_group = mock.Mock()
        actor._find_target_group.return_value = helper.tornado_value('arn')
        actor._remove = mock.Mock()
        actor._remove.return_value = helper.tornado_value(mock.Mock())
        yield actor._execute()
        actor._remove.assert_called_with('arn', ['i-test'])

    @testing.gen_test
    def test_execute_self(self):
        actor = elbv2_actor.DeregisterInstance('UTA', {
            'target_group': 'elb-test',
            'region': 'us-east-1'})

        actor._find_target_group = mock.Mock()
        actor._find_target_group.return_value = helper.tornado_value('arn')
        actor._get_meta_data = helper.mock_tornado('i-test')
        actor._remove = mock.Mock()
        actor._remove.return_value = helper.tornado_value(mock.Mock())
        yield actor._execute()
        actor._remove.assert_called_with('arn', ['i-test'])
