import logging
import mock

from tornado import testing

from kingpin.actors import exceptions
from kingpin.actors.rightscale import base
from kingpin.actors.rightscale import deployment
from kingpin.actors.test import helper

log = logging.getLogger(__name__)


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
        with mock.patch.object(self.actor._client, 'create_resource'):
            yield self.actor._execute()

            self.assertEquals(self.actor._client.create_resource.call_count, 0)

    @testing.gen_test
    def test_exec(self):
        with mock.patch.object(self.actor._client, 'create_resource') as cr:
            cr.return_value = helper.tornado_value()
            yield self.actor._execute()

            self.assertEquals(self.actor._client.create_resource.call_count, 1)

    @testing.gen_test
    def test_exec_duplicate(self):
        with mock.patch.object(self.actor._client, 'create_resource') as cr:
            cr.return_value = helper.tornado_value()
            cr.side_effect = Exception('422: Client error')
            with self.assertRaises(exceptions.UnrecoverableActorFailure):
                yield self.actor._execute()
