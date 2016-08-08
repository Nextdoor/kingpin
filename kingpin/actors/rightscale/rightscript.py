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

"""
:mod:`kingpin.actors.rightscale.rightscript`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
"""

import logging

from tornado import gen

from kingpin import utils
from kingpin.actors import exceptions
from kingpin.actors.rightscale import base
from kingpin.actors.utils import dry
from kingpin.constants import REQUIRED, STATE

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


class RightScript(base.RightScaleBaseActor):

    """Manages the state of a RightScale Script

    Options match the documentation in RightScale:
    http://reference.rightscale.com/api1.5/resources/ResourceRightScripts.html

    **Options**

    :name:
      (str) The name of the RightScript.

    :description:
      (str) Optional description of the RightScript.

    :packages:
      (list, str) A list of packages that need to be installed in order to run
      the script.

    :source:
      (str) A file name with the contents of the script you want to upload.

    :commit:
      (str) Optional comment used to commit the revision if Kingpin makes any
      changes at all.

    **Examples**

    Create a high network activity alert on my-array:

    .. code-block:: json

        { "actor": "rightscale.alerts.Create",
          "options": {
            "name": "Set Hostname",
            "ensure": "present",
            "commit": "yep",
            "description": "Set the hostname to something usable",
            "packages": "hostname sed curl",
            "source": "./set_hostname.sh"
          }
        }
    """

    all_options = {
        'name': (str, REQUIRED, 'Name of the RightScript to manage'),
        'state': (STATE, 'present',
                  'The condition (operator) in the condition sentence.'),
        'commit': (str, None, 'Commit the RightScript revision on-change.'),
        'description': (str, None, 'The description of the RightScript.'),
        'packages': (str, None, 'Space separaged list of packages to install'),
        'source': (str, REQUIRED, 'File containing the script contents.'),
    }

    desc = 'RightScript: {name}'

    def __init__(self, *args, **kwargs):
        """Validate the user-supplied parameters at instantiation time."""
        super(RightScript, self).__init__(*args, **kwargs)
        self.changed = False
        self._source = self._read_source()
        self._params = self._generate_rightscale_params(
            prefix='right_script',
            params={
                'description': self.option('description'),
                'name': self.option('name'),
                'packages': self.option('packages'),
                'source': self._source,
            })

    def _read_source(self):
        """Reads in a RightScript source file.

        Reads in the file contents, and swaps in any tokens that may have
        been left in the script.

        args:
            source: Path to the script

        returns:
            <string contents of the script>
        """
        source = self.option('source')

        try:
            fh = open(source)
            raw = fh.read()
        except IOError as e:
            raise exceptions.InvalidOptions('Error reading script %s: %s' %
                                            (source, e))

        try:
            parsed = utils.populate_with_tokens(raw, self._init_tokens)
        except LookupError as e:
            raise exceptions.InvalidOptions('Error parsing tokens in %s: %s' %
                                            (source, e))

        return parsed

    @gen.coroutine
    def _get_script(self, name):
        """Search for an RightScript by-name and return the resource.

        Note: A non-exact resource match is used below so that we return all of
        the RightSCripts that are matched by name. This method returns the
        resources in a list.

        Args:
            name: RightScale RightScript Name

        Return:
            <rightcale.Resource objects>
        """
        log.debug('Searching for RightScript matching: %s' % name)
        found = yield self._client.find_by_name_and_keys(
            self._client._client.right_scripts, exact=True, name=name)

        if not found:
            log.debug('RightScript matching "%s" could not be found.' % name)
            return

        log.debug('Got RightScript: %s' % found[0])
        raise gen.Return(found[0])

    @gen.coroutine
    @dry('Would have created script {name}')
    def _create_script(self, name):
        """Creates a RightScript.

        args:
            name: The name of the script to create
        """
        script = yield self._client.create_resource(
            self._client._client.right_scripts, self._params)
        self.changed = True
        raise gen.Return(script)

    @gen.coroutine
    @dry('Would have deleted script {name}')
    def _delete_script(self, name):
        """Creates a RightScript.

        args:
            name: The name of the script to delete
        """
        script = yield self._get_script(name)
        if not script:
            raise gen.Return()

        yield self._client.destroy_resource(script)
        self.changed = True
        raise gen.Return()

    @gen.coroutine
    @dry('Would have updated the RightScript parameters')
    def _update_params(self, script):
        self.log.info('Updating RightScript parameters...')
        script = yield self._client.update(script, self._params)
        self.changed = True
        raise gen.Return(script)

    @gen.coroutine
    def _ensure_description(self, script):
        existing = script.soul['description']
        new = self.option('description')

        if existing == new:
            self.log.debug('Descriptions match')
            raise gen.Return()

        self.log.warning('Descriptions do not match')
        yield self._update_params(script)

    @gen.coroutine
    def _ensure_packages(self, script):
        existing = script.soul['packages']
        new = self.option('packages')

        if existing == new:
            self.log.debug('Packages match')
            raise gen.Return()

        self.log.warning('Packages do not match')
        yield self._update_params(script)

    @gen.coroutine
    def _ensure_source(self, script):
        existing = yield self._client.make_generic_request(script.source.path)
        new = self._source

        if existing == new:
            self.log.debug('Sources match')
            raise gen.Return()

        self.log.warning('Source does not match')
        yield self._update_params(script)

    @gen.coroutine
    @dry('Would have committed HEAD to a revision')
    def _commit(self, script, message):
        self.log.info('Committing a new revision')

        ret = yield self._client.commit_resource(
            res=script, res_type=self._client._client.right_scripts,
            params={'right_script[commit_message]': message})

        self.log.info('Committed revision %s' % ret.soul['revision'])

    @gen.coroutine
    def _ensure_script(self):
        """Creates or deletes a RightScript depending on the state"""
        state = self.option('state')
        name = self.option('name')

        self.log.info('Ensuring that RightScript %s is %s' % (name, state))
        script = yield self._get_script(name)

        if state == 'absent' and script is None:
            self.log.debug('RightScript does not exist')
        elif state == 'absent' and script:
            yield self._delete_script(name=name)
            script = None
        elif state == 'present' and script is None:
            script = yield self._create_script(name=name)
        elif state == 'present' and script:
            self.log.debug('RightScript exists')

        raise gen.Return(script)

    @gen.coroutine
    def _execute(self):
        script = yield self._ensure_script()

        # If we're deleting the MCI, then there is no need to continue
        # after we've done that.
        if self.option('state') == 'absent':
            raise gen.Return()

        # Ensure that the description is up to date
        yield self._ensure_description(script)

        # Ensure that the script contents are correct
        yield self._ensure_source(script)

        # Ensure the package lists match
        yield self._ensure_packages(script)

        # Finally, if we're committing and a change was made, commit!
        if self.changed and self.option('commit'):
            yield self._commit(script, self.option('commit'))

        raise gen.Return()
