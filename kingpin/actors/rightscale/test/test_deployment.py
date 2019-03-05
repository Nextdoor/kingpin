import logging
import mock

from tornado import testing

from kingpin.actors import exceptions
from kingpin.actors.rightscale import base
from kingpin.actors.rightscale import deployment
from kingpin.actors.test import helper

log = logging.getLogger(__name__)


class TestDeploymentBaseActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestDeploymentBaseActor, self).setUp()
        base.TOKEN = 'unittest'
        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()

    @testing.gen_test
    def test_find_deployment(self):
        actor = deployment.DeploymentBaseActor('Test', {})
        actor._client = self.client_mock

        with mock.patch.object(actor._client, 'find_by_name_and_keys') as cr:
            cr.return_value = helper.tornado_value()
            yield actor._find_deployment('Unit Test')
            self.assertEqual(
                actor._client.find_by_name_and_keys.call_count, 1)


class TestDeploymentCreateActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestDeploymentCreateActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = deployment.Create('Test',
                                       {'name': 'unit-test',
                                        'description': 'unit test',
                                        'server_tag_scope': 'deployment'})

        # Patch the actor so that we use the client mock
        self.client_mock = mock.MagicMock()
        self.actor._client = self.client_mock

    @testing.gen_test
    def test_bad_scope(self):
        with self.assertRaises(exceptions.InvalidOptions):
            deployment.Create('Test', {'name': 'test',
                                       'server_tag_scope': 'fail'})

    @testing.gen_test
    def test_exec_dry(self):
        self.actor._dry = True
        self.actor._find_deployment = helper.mock_tornado(None)
        self.actor._client.create_resource = helper.mock_tornado()
        yield self.actor._execute()
        self.assertEqual(self.actor._client.create_resource._call_count, 0)

    @testing.gen_test
    def test_exec(self):
        self.actor._find_deployment = helper.mock_tornado(None)
        self.actor._client.create_resource = helper.mock_tornado()
        yield self.actor._execute()
        self.assertEqual(self.actor._client.create_resource._call_count, 1)

    @testing.gen_test
    def test_exec_duplicate(self):
        self.actor._find_deployment = helper.mock_tornado('found_deployment')

        with self.assertRaises(exceptions.InvalidOptions):
            yield self.actor._execute()


class TestDeploymentDestroyActor(testing.AsyncTestCase):

    def setUp(self, *args, **kwargs):
        super(TestDeploymentDestroyActor, self).setUp()
        base.TOKEN = 'unittest'

        # Create the actor
        self.actor = deployment.Destroy('Test', {'name': 'unit-test'})

        # Patch the actor so that we use the client mock
        self.actor._client = mock.Mock()
        self.actor._find_deployment = helper.mock_tornado(mock.MagicMock())
        self.actor._client.show = helper.mock_tornado(mock.MagicMock())

    @testing.gen_test
    def test_exec_dry(self):
        self.actor._dry = True
        self.actor._client.destroy_resource = helper.mock_tornado()
        yield self.actor._execute()

        self.assertEqual(self.actor._client.destroy_resource._call_count, 0)

    @testing.gen_test
    def test_exec(self):
        self.actor._client.destroy_resource = helper.mock_tornado()
        yield self.actor._execute()

        self.assertEqual(self.actor._client.destroy_resource._call_count, 1)

    @testing.gen_test
    def test_exec_not_found(self):
        self.actor._client.destroy_resource = helper.mock_tornado()
        self.actor._find_deployment = helper.mock_tornado(None)
        with self.assertRaises(exceptions.InvalidOptions):
            yield self.actor._execute()

        self.assertEqual(self.actor._client.destroy_resource._call_count, 0)
