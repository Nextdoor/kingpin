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
:mod:`kingpin.actors.rightscale.deployment`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. _Deployments:
    http://reference.rightscale.com/api1.5/resources/ResourceDeployments.html
"""

import logging

from tornado import gen

from kingpin.actors import exceptions
from kingpin.actors.rightscale import base
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Mikhail Simin <mikhail@nextdoor.com>'


class DeploymentBaseActor(base.RightScaleBaseActor):

    """Abstract Deployment Actor that provides some utility methods."""

    @gen.coroutine
    def _find_deployment(self, name):

        dep = yield self._client.find_by_name_and_keys(
            collection=self._client._client.deployments,
            name=name)

        raise gen.Return(dep)


class Create(DeploymentBaseActor):

    """Creates a RightScale deployment.

    **Options**

    :name:
      The name of the deployment to be created.

    :description:
       The description of the deployment to be created.
       (*optional*)

    :server_tag_scope:
       The routing scope for tags for servers in the deployment.
       Can be 'deployment' or 'account'
       (*optional*, default: deployment)
    """

    all_options = {
        'name': (str, REQUIRED, 'The name of the deployment to be created.'),
        'description': (
            str, '',
            'The description of the deployment to be created.'),
        'server_tag_scope': (
            str, '',
            'The routing scope for tags for servers in the deployment.')
    }

    def __init__(self, *args, **kwargs):
        """Validate the user-supplied parameters at instantiation time."""

        super(Create, self).__init__(*args, **kwargs)

        allowed_scopes = ('deployment', 'account', '')

        scope = self.option('server_tag_scope')
        if scope not in allowed_scopes:
            raise exceptions.InvalidOptions(
                'server_tag_scope "%s" is not one of: %s' % (scope,
                                                             allowed_scopes))

    @gen.coroutine
    def _execute(self):

        dep = yield self._find_deployment(self.option('name'))
        if dep:
            raise exceptions.InvalidOptions(
                'Deployment "%s" already exists.' % self.option('name'))

        params = {'name': self.option('name'),
                  'description': self.option('description')}

        if self.option('server_tag_scope'):
            params['server_tag_scope'] = self.option('server_tag_scope')

        params = self._generate_rightscale_params('deployment', params)

        if self._dry:
            self.log.info('Would create a deployment %s' % self.option('name'))
            self.log.debug('Deployment params: %s' % params)
            raise gen.Return()

        self.log.info('Creating deployment %s' % self.option('name'))

        yield self._client.create_resource(
            self._client._client.deployments, params)


class Clone(DeploymentBaseActor):

    """Clones a RightScale deployment.

    **Options**

    :clone:
      The name of the deployment to clone.

    :name:
      The name of the deployment to create.

    :description:
       The description of the new deployment.
       (*optional*)

    :server_tag_scope:
       The routing scope for tags for servers in the deployment.
       Can be 'deployment' or 'account'
       (*optional*, default: deployment)
    """

    all_options = {
        'clone': (str, REQUIRED, 'The name of the deployment to clone.'),
        'name': (str, REQUIRED, 'The name of the deployment to create.'),
        'description': (
            str, '',
            'The description of the deployment to be cloned.'),
        'server_tag_scope': (
            str, '',
            'The routing scope for tags for servers in the deployment.'),
        'delete_servers': (
            bool, False, 'Delete servers and arrays after cloning')
    }

    def __init__(self, *args, **kwargs):
        """Validate the user-supplied parameters at instantiation time."""

        super(Clone, self).__init__(*args, **kwargs)

        allowed_scopes = ('deployment', 'account', '')

        scope = self.option('server_tag_scope')
        if scope not in allowed_scopes:
            raise exceptions.InvalidOptions(
                'server_tag_scope "%s" is not one of: %s' % (scope,
                                                             allowed_scopes))

    @gen.coroutine
    def _execute(self):

        dep = yield self._find_deployment(self.option('clone'))
        if not dep:
            raise exceptions.InvalidOptions(
                'Deployment "%s" does not exist.' % self.option('clone'))
        self.log.info('Found "%s" to clone.' % self.option('clone'))

        newdep = yield self._find_deployment(self.option('name'))
        if newdep:
            self.log.error('Cannot create new "%s".' % self.option('name'))
            raise exceptions.InvalidOptions(
                'Deployment "%s" already exists.' % self.option('name'))

        optional_params = {'name', 'description', 'server_tag_scope'}
        params = {}
        for p in optional_params:
            if self.option(p):
                params[p] = self.option(p)

        params = self._generate_rightscale_params('deployment', params)

        if self._dry:
            self.log.info('Would clone a deployment %s' % self.option('name'))
            self.log.debug('Deployment params: %s' % params)
            if self.option('delete_servers'):
                servers = dep.servers.show()
                self.log.info('Found %s servers' % len(servers))
                for s in servers:
                    self.log.info('Would delete %s' % s.soul['name'])

                arrays = dep.server_arrays.show()
                self.log.info('Found %s arrays' % len(arrays))
                for a in arrays:
                    self.log.info('Would delete %s' % a.soul['name'])
            if self.option('rename_servers'):
                servers = dep.servers.show()
                self.log.info('Found %s servers' % len(servers))
                for s in servers:
                    self.log.info('Would rename %s' % s.soul['name'])

                arrays = dep.server_arrays.show()
                self.log.info('Found %s arrays' % len(arrays))
                for a in arrays:
                    self.log.info('Would rename %s' % a.soul['name'])

            raise gen.Return()

        self.log.info('Creating deployment %s' % self.option('name'))

        dep_id = self._client.get_res_id(dep)
        newdep = self._client._client.deployments.clone(
            res_id=dep_id, params=params)

        if self.option('delete_servers'):
            servers = newdep.servers.show()
            self.log.info('Found %s servers' % len(servers))
            for s in servers:
                self.log.info('Deleting %s' % s.soul['name'])
                yield self._client.destroy_resource(s)

            arrays = newdep.server_arrays.show()
            self.log.info('Found %s arrays' % len(arrays))
            for a in arrays:
                self.log.info('Deleting %s' % a.soul['name'])
                yield self._client.destroy_resource(a)

            self.log.info('Done deleting servers and arrays.')
        if self.option('rename_servers'):
            servers = newdep.servers.show()
            self.log.info('Found %s servers' % len(servers))
            for s in servers:
                new_name = '%s-%s-%s' % (
                    self.option('rename_servers')['prefix'],
                    s.soul['name'],
                    self.option('rename_servers')['suffix'])
                self.log.info('Renaming %s => %s' % (s.soul['name'], new_name))
                yield self._client.update(s, {'server[name]': new_name})

            arrays = newdep.server_arrays.show()
            self.log.info('Found %s arrays' % len(arrays))
            for a in arrays:
                self.log.info('Deleting %s' % a.soul['name'])
                new_name = '%s-%s-%s' % (
                    self.option('rename_servers')['prefix'],
                    a.soul['name'],
                    self.option('rename_servers')['suffix'])
                self.log.info('Renaming %s => %s' % (a.soul['name'], new_name))
                yield self._client.update(a, {'server_array[name]': new_name})

            self.log.info('Done deleting servers and arrays.')


class Destroy(DeploymentBaseActor):

    """Deletes a RightScale deployment.

    **Options**

    :name:
      The name of the deployment to be deleted.
    """

    all_options = {
        'name': (str, REQUIRED, 'The name of the deployment to be deleted.'),
    }

    @gen.coroutine
    def _execute(self):

        dep = yield self._find_deployment(self.option('name'))
        if not dep:
            raise exceptions.InvalidOptions(
                'Deployment "%s" does not exist.' % self.option('name'))

        info = (yield self._client.show(dep.self)).soul

        if self._dry:
            self.log.info('Would delete deployment %s' % info['name'])
            raise gen.Return()

        self.log.info('Deleting deployment %s' % info['name'])
        yield self._client.destroy_resource(dep)
