import logging

from botocore import exceptions as botocore_exceptions
from tornado import testing
import mock

from kingpin.actors import exceptions
from kingpin.actors.aws import settings
from kingpin.actors.aws.iam import certs
import importlib

log = logging.getLogger(__name__)


class TestUploadCert(testing.AsyncTestCase):

    def setUp(self):
        super(TestUploadCert, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        importlib.reload(certs)

    @testing.gen_test
    def test_execute(self):
        actor = certs.UploadCert(
            'Unit Test',
            {'name': 'test',
             'public_key_path': 'test',
             'private_key_path': 'test',
             'cert_chain_path': 'test'}
        )
        actor.iam_conn = mock.Mock()

        actor.readfile = mock.Mock()
        actor.iam_conn.upload_server_cert.side_effect = [
            None
        ]
        yield actor._execute()

        # call count is 1 -- one extra retry due to BotoServerError above.
        self.assertEqual(actor.iam_conn.upload_server_cert.call_count, 1)
        actor.iam_conn.upload_server_cert.assert_called_with(
            path=None,
            private_key=actor.readfile(),
            cert_body=actor.readfile(),
            cert_name='test',
            cert_chain=actor.readfile())

    @testing.gen_test
    def test_execute_dry(self):
        actor = certs.UploadCert(
            'Unit Test',
            {'name': 'test',
             'public_key_path': 'test',
             'private_key_path': 'test',
             'cert_chain_path': 'test'},
            dry=True
        )
        actor.iam_conn = mock.Mock()

        actor.readfile = mock.Mock()
        open_patcher = mock.patch('%s.open' % actor.__module__,
                                  create=True)
        with open_patcher:
            yield actor._execute()

        self.assertEqual(actor.iam_conn.upload_server_cert.call_count, 0)


class TestDeleteCert(testing.AsyncTestCase):

    def setUp(self):
        super(TestDeleteCert, self).setUp()
        settings.AWS_ACCESS_KEY_ID = 'unit-test'
        settings.AWS_SECRET_ACCESS_KEY = 'unit-test'
        importlib.reload(certs)

    @testing.gen_test(timeout=60)
    def test_delete_cert_dry(self):
        actor = certs.DeleteCert('Test', {'name': 'test'}, dry=True)
        actor.iam_conn = mock.Mock()

        yield actor.execute()

        actor.iam_conn.get_server_certificate.assert_called_with('test')
        self.assertEqual(actor.iam_conn.get_server_certificate.call_count, 1)

        err = botocore_exceptions.ClientError(
            {'Error': {'Code': '400'}}
        )
        actor.iam_conn.get_server_certificate.side_effect = err

        with self.assertRaises(exceptions.UnrecoverableActorFailure):
            yield actor.execute()

    @testing.gen_test(timeout=60)
    def test_delete_cert(self):
        actor = certs.DeleteCert(
            'Test',
            {'name': 'test'})
        actor.iam_conn = mock.Mock()

        yield actor.execute()
