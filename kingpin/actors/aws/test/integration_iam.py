"""Simple integration tests for the AWS IAM actors."""

from nose.plugins.attrib import attr
import logging

from tornado import testing

from kingpin.actors.aws import iam

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'

log = logging.getLogger(__name__)
logging.getLogger('boto').setLevel(logging.INFO)


class IntegrationIAM(testing.AsyncTestCase):

    integration = True

    cert_name = 'kingpin-integration-test'
    region = 'us-east-1'

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_01a_upload_cert_dry(self):
        actor = iam.UploadCert(
            'Test',
            {'name': self.cert_name,
             'public_key_path': 'examples/test/server.pem',
             'private_key_path': 'examples/test/server.key'},
            dry=True)

        yield actor.execute()

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_01b_upload_cert(self):
        actor = iam.UploadCert(
            'Test',
            {'name': self.cert_name,
             'public_key_path': 'examples/test/server.pem',
             'private_key_path': 'examples/test/server.key'})

        yield actor.execute()

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_02a_delete_cert_dry(self):
        actor = iam.DeleteCert(
            'Test',
            {'name': self.cert_name},
            dry=True)

        yield actor.execute()

    @attr('integration')
    @testing.gen_test(timeout=60)
    def integration_02b_delete_cert(self):
        actor = iam.DeleteCert(
            'Test',
            {'name': self.cert_name})

        yield actor.execute()
