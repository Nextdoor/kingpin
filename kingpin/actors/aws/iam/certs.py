# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Copyright 2018 Nextdoor.com, Inc

"""
:mod:`kingpin.actors.aws.iam.certs`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

import logging

from boto.exception import BotoServerError
from tornado import concurrent
from tornado import gen

from kingpin.actors import exceptions
from kingpin.actors.aws.iam import base
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'


# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = concurrent.futures.ThreadPoolExecutor(10)


class UploadCert(base.IAMBaseActor):

    """Uploads a new SSL Cert to AWS IAM.

    **Options**

    :private_key_path:
      (str) Path to the private key.

    :path:
      (str) The AWS "path" for the server certificate. Default: "/"

    :public_key_path:
      (str) Path to the public key certificate.

    :name:
      (str) The name for the server certificate.

    :cert_chain_path:
      (str) Path to the certificate chain. Optional.

    **Example**

    .. code-block:: json

       { "actor": "aws.iam.UploadCert",
         "desc": "Upload a new cert",
         "options": {
           "name": "new-cert",
           "private_key_path": "/cert.key",
           "public_key_path": "/cert.pem",
           "cert_chain_path": "/cert-chain.pem"
         }
       }

    **Dry run**

    Checks that the passed file paths are valid. In the future will also
    validate that the files are of correct format and content.
    """

    all_options = {
        'name': (str, REQUIRED, 'The name for the server certificate.'),
        'public_key_path': (str, REQUIRED,
                            'Path to the public key certificate.'),
        'private_key_path': (str, REQUIRED, 'Path to the private key.'),
        'cert_chain_path': (str, None, 'Path to the certificate chain.'),
        'path': (str, None, 'The path for the server certificate.')
    }

    @gen.coroutine
    def _upload(self, cert_name, cert_body, private_key, cert_chain, path):
        """Create a new server certificate in AWS IAM."""
        yield self.api_call(
            self.iam_conn.upload_server_cert,
            cert_name=cert_name,
            cert_body=cert_body,
            private_key=private_key,
            cert_chain=cert_chain,
            path=path)

    @gen.coroutine
    def _execute(self):
        """Gather all the cert data and upload it.

        The `boto` library requires actual cert contents, but this actor
        expects paths to files.
        """
        # Gather needed cert data
        cert_chain_body = None
        if self.option('cert_chain_path'):
            cert_chain_body = self.readfile(self.option('cert_chain_path'))

        cert_body = self.readfile(self.option('public_key_path'))
        private_key = self.readfile(self.option('private_key_path'))

        # Upload it
        if self._dry:
            self.log.info('Would upload cert "%s"' % self.option('name'))
            raise gen.Return()

        self.log.info('Uploading cert "%s"' % self.option('name'))
        yield self._upload(
            cert_name=self.option('name'),
            cert_body=cert_body,
            private_key=private_key,
            cert_chain=cert_chain_body,
            path=self.option('path'))


class DeleteCert(base.IAMBaseActor):

    """Delete an existing SSL Cert in AWS IAM.

    **Options**

    :name:
      (str) The name for the server certificate.

    **Example**

    .. code-block:: json

       { "actor": "aws.iam.DeleteCert",
         "desc": "Run DeleteCert",
         "options": {
           "name": "fill-in"
         }
       }

    **Dry run**

    Will find the cert by name or raise an exception if it's not found.
    """

    all_options = {
        'name': (str, REQUIRED, 'The name for the server certificate.')
    }

    @gen.coroutine
    def _find_cert(self, name):
        """Find a cert by name."""

        self.log.debug('Searching for cert "%s"...' % name)
        try:
            yield self.api_call(self.iam_conn.get_server_certificate, name)
        except BotoServerError as e:
            raise exceptions.UnrecoverableActorFailure(
                'Could not find cert %s. Reason: %s' % (name, e))

    @gen.coroutine
    def _delete(self, cert_name):
        """Delete a server certificate in AWS IAM."""
        yield self.api_call(self.iam_conn.delete_server_cert, cert_name)

    @gen.coroutine
    def _execute(self):
        if self._dry:
            self.log.info('Checking that the cert exists...')
            yield self._find_cert(self.option('name'))
            self.log.info('Would delete cert "%s"' % self.option('name'))
            raise gen.Return()

        self.log.info('Deleting cert "%s"' % self.option('name'))
        yield self._delete(cert_name=self.option('name'))
