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


class RightScript(base.EnsurableRightScaleBaseActor):

    """Manages the state of a RightScale Script

    Options match the documentation in RightScale:
    http://reference.rightscale.com/api1.5/resources/ResourceRightScripts.html

    **RightScript Inputs**
    RightScripts have a concept of "inputs" ... pieces of data that are
    supplied to the script on-startup to help configure your instance. By
    *default*, RightScale parses the script you attach and automatically
    exposes inputs for you:

    http://docs.rightscale.com/cm/rs101/understanding_inputs.html

    RightScale has recently released an automatic script parser that looks for
    YAML-formatted comments in your script and reads the metadata from the
    comments. This is much more powerful and allows you to be explicit about
    the inputs required for your script to function.

    http://docs.rightscale.com/cm/dashboard/design/rightscripts/rightscripts_metadata_comments.html

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
      Script should contain the *RightScale Metadata Comments* (see above)
      which will automatically handle configuring the inputs for your script.

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

    unmanaged_options = ['commit', 'name']

    desc = 'RightScript: {name}'

    def __init__(self, *args, **kwargs):
        """Validate the user-supplied parameters at instantiation time."""
        super(RightScript, self).__init__(*args, **kwargs)
        self.changed = False

        # The rightscale API allows you to push an invalid list of packages
        # (multiple spaces, newlines, etc). We need to sanitize the list
        # quickly first.
        if self.option('packages'):
            self._options['packages'] = ' '.join(
                self.option('packages').split())

        self._desired_source = self._read_source()
        self._desired_params = self._generate_rightscale_params(
            prefix='right_script',
            params={
                'description': self.option('description'),
                'name': self.option('name'),
                'packages': self.option('packages'),

                # Passing in right_script[source] is required at creation time
                # .. but we can't pass in large scripts this way. Instead, we
                # pass in bogus text here, and rely on set_source() to properly
                # update the source with a special API endpoint. This value is
                # stripped out of any update_params() calls, so its only used
                # at creation time.
                'source': 'bogus'
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
    def _precache(self):
        # First go off and find our script object
        name = self.option('name')
        log.debug('Searching for RightScript matching: %s' % name)
        found = yield self._client.find_by_name_and_keys(
            self._client._client.right_scripts, exact=True, name=name)

        if not found:
            log.debug('RightScript matching "%s" could not be found.' % name)
            self.script = None
            self.source = None
            raise gen.Return()

        # It was found, so save a reference to the object
        if not isinstance(found, list):
            found = [found]

        log.debug('Got RightScript: %s' % found[0])
        self.script = found[0]

        # Next, get the source of the script
        self.source = yield self._client.make_generic_request(
            self.script.source.path)

    @gen.coroutine
    def _set_state(self):
        """Creates a RightScript.

        args:
            name: The name of the script to create
        """
        if self._dry:
            self.log.warning('Would have set RightScript state: %s' %
                             self.option('state'))
            self.script = None
            self.changed = True
            raise gen.Return()

        if self.option('state') == 'absent':
            if not self.script:
                raise gen.Return()

            self.log.info('Destroying RightScript')
            yield self._client.destroy_resource(self.script)
            self.script = None
            self.changed = True
            raise gen.Return()

        self.log.info('Creating RightScript')
        self.script = yield self._client.create_resource(
            self._client._client.right_scripts, self._desired_params)
        self.changed = True

    @gen.coroutine
    def _get_state(self):
        if self.script is None:
            raise gen.Return('absent')

        raise gen.Return('present')

    @gen.coroutine
    @dry('Would have updated the RightScript parameters')
    def _update_params(self):
        self.log.info('Updating RightScript parameters...')
        params = [t for t in self._desired_params if
                  t[0] != 'right_script[source]']
        self.script = yield self._client.update(self.script, params)
        self.changed = True

    @gen.coroutine
    @dry('Would have updated the RightScale Source')
    def _set_source(self):
        self.log.info('Updating RightScript source...')
        self.script = yield self._client.update(
            self.script,
            self._desired_source,
            sub_resource='source')
        self.changed = True

    @gen.coroutine
    def _get_source(self):
        raise gen.Return(self.source)

    @gen.coroutine
    def _compare_source(self):
        existing = yield self._get_source()
        equals = (self._desired_source == existing)
        raise gen.Return(equals)

    @gen.coroutine
    def _set_description(self):
        self.log.warning('Descriptions do not match')
        yield self._update_params()

    @gen.coroutine
    def _get_description(self):
        if self.script is None or 'description' not in self.script.soul:
            raise gen.Return()

        raise gen.Return(self.script.soul['description'])

    @gen.coroutine
    def _set_packages(self):
        self.log.warning('Packages do not match')
        yield self._update_params()

    @gen.coroutine
    def _get_packages(self):
        if self.script is None or 'packages' not in self.script.soul:
            raise gen.Return()

        raise gen.Return(self.script.soul['packages'])

    @gen.coroutine
    @dry('Would have committed HEAD to a revision')
    def _commit(self):
        self.log.info('Committing a new revision')

        ret = yield self._client.commit_resource(
            res=self.script, res_type=self._client._client.right_scripts,
            params={'right_script[commit_message]': self.option('commit')})

        self.log.info('Committed revision %s' % ret.soul['revision'])

    @gen.coroutine
    def _execute(self):
        yield super(RightScript, self)._execute()

        if self.option('state') == 'absent':
            raise gen.Return()

        # Finally, if we're committing and a change was made, commit!
        if self.changed and self.option('commit'):
            yield self._commit()
