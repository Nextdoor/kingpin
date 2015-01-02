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
# Copyright 2014 Nextdoor.com, Inc

"""AWS IAM Actors"""

import logging
import re
import time

from concurrent import futures
from tornado import concurrent
from tornado import gen
from tornado import ioloop
import boto.iam.connection

from kingpin import utils
from kingpin.actors import base
from kingpin.actors import exceptions
from kingpin.actors.aws import settings as aws_settings
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'


# This executor is used by the tornado.concurrent.run_on_executor()
# decorator. We would like this to be a class variable so its shared
# across RightScale objects, but we see testing IO errors when we
# do this.
EXECUTOR = futures.ThreadPoolExecutor(10)


class IAMBaseActor(base.BaseActor):

    # Get references to existing objects that are used by the
    # tornado.concurrent.run_on_executor() decorator.
    ioloop = ioloop.IOLoop.current()
    executor = EXECUTOR

    def __init__(self, *args, **kwargs):
        """Create the connection object."""
        super(IAMBaseActor, self).__init__(*args, **kwargs)

        if not (aws_settings.AWS_ACCESS_KEY_ID and
                aws_settings.AWS_SECRET_ACCESS_KEY):
            raise exceptions.InvalidCredentials(
                'AWS settings imported but not all credentials are supplied. '
                'AWS_ACCESS_KEY_ID: %s, AWS_SECRET_ACCESS_KEY: %s' % (
                    aws_settings.AWS_ACCESS_KEY_ID,
                    aws_settings.AWS_SECRET_ACCESS_KEY))

        self.conn = boto.iam.connection.IAMConnection(
            aws_settings.AWS_ACCESS_KEY_ID,
            aws_settings.AWS_SECRET_ACCESS_KEY)


class UploadCert(IAMBaseActor):

    """Uploads a new SSL Cert to AWS IAM.
    
    http://boto.readthedocs.org/en/latest/ref/iam.html
    #boto.iam.connection.IAMConnection.upload_server_cert
    """

    all_options = {
        'name': (str, REQUIRED, 'The name for the server certificate.'),
        'public_key_path': (str, REQUIRED, 'Path to the public key certificate.'),
        'private_key_path': (str, REQUIRED, 'Path to the private key.'),
        'cert_chain_path': (str, None, 'Path to the certificate chain.'),
        'body_path': (str, None, 'The path for the server certificate.')
    }

    @gen.coroutine
    def _execute(self):
        self.conn.upload_server_cert(
            cert_name=self.option('name'),
            cert_body=open(self.option('public_key_path')).read(),
            private_key=open(self.option('private_key_path')).read(),
            cert_chain=open(self.option('cert_chain_path')).read(),
            path=open(self.option('body_path')).read())

