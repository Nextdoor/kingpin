import logging

from tornado import testing
import mock

from kingpin.actors.aws import settings
from kingpin.actors.aws import iam

log = logging.getLogger(__name__)


class TestUploadCert(testing.AsyncTestCase):

    def setUp(self):
        super(TestUploadCert, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'

    @testing.gen_test
    def test_execute(self):
        actor = iam.UploadCert(
            'Unit Test',
            {'name': 'test',
             'public_key_path': 'test',
             'private_key_path': 'test',
             'cert_chain_path': 'test'}
        )
        actor.conn = mock.Mock()

        open_patcher = mock.patch('%s.open' % actor.__module__,
                                  create=True)
        with open_patcher as mocked_open:
            yield actor._execute()

        self.assertEquals(actor.conn.upload_server_cert.call_count, 1)
        actor.conn.upload_server_cert.assert_called_with(
            path=None,
            private_key=mocked_open().read(),
            cert_body=mocked_open().read(),
            cert_name='test',
            cert_chain=mocked_open().read())

    @testing.gen_test
    def test_execute_dry(self):
        actor = iam.UploadCert(
            'Unit Test',
            {'name': 'test',
             'public_key_path': 'test',
             'private_key_path': 'test',
             'cert_chain_path': 'test'},
            dry=True
        )
        actor.conn = mock.Mock()

        open_patcher = mock.patch('%s.open' % actor.__module__,
                                  create=True)
        with open_patcher:
            yield actor._execute()

        self.assertEquals(actor.conn.upload_server_cert.call_count, 0)
