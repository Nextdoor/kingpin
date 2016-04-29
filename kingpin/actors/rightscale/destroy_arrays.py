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
:mod:`kingpin.actors.rightscale.destroy_arrays`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. _ResourceInstances:
   http://reference.rightscale.com/api1.5/resources/
   ResourceInstances.html#update
"""

import logging

from tornado import gen
import mock

from kingpin.actors.rightscale import base, server_array
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Andrew S. Brown <asbrown@nextdoor.com>'


class DestroyMany(base.RightScaleBaseActor):

    """Destroys a set of RightScale Server Arrays.

    Destroys ServerArray in RightScale matching a given name.

    :target:
      The name(s) of the ServerArrays to destroy

    :exclude:
      The name(s) of any arrays to exclude (default: [])

    **Examples**

    Destroy 'my-arrays':

    .. code-block:: json

       { "desc": "Destroy m- arrayss",
         "actor": "rightscale.server_array.DestroyMany",
         "options": {
           "target": ["my-array"],
           "exact": false,
           "exclude": ["my-array-excluded"]
         }
       }


    **Dry Mode**

    In Dry mode this actor lists the arrays that will be destroyed and the
    excluded arrays that will not.
    """

    all_options = {
        'target': ((list, str), REQUIRED,
                   'Names of the ServerArrays to destroy.'),
        'exclude': ((list, str), [], 'Names of server arrays to keep.'),
    }

    @gen.coroutine
    def _execute(self):
        target_arrays = []
        excluded_arrays = set()

        targets = self.option('target')
        if not isinstance(targets, list):
            targets = [targets]

        for target in targets:
            arrays = yield self._find_server_arrays(target, raise_on=None)

            if not isinstance(arrays, list):
                arrays = [arrays]

            target_arrays.extend(a.soul['name'] for a in arrays)

        excludes = self.option('exclude')
        if not isinstance(excludes, list):
            excludes = [excludes]

        for exclude in excludes:
            arrays = yield self._find_server_arrays(exclude, raise_on=None)

            if not isinstance(arrays, list):
                arrays = [arrays]

            excluded_arrays.update(a.soul['name'] for a in arrays)

        for target in target_arrays:
            if target in excluded_arrays:
                self.log.info('Excluding array "%s" from destroy.' % target)
                continue

            destroyer = server_array.Destroy(
                'Destroy',
                {'array': target},
                dry=self._dry,
                warn_on_failure=self._warn_on_failure)
            yield destroyer.execute()

        raise gen.Return()
