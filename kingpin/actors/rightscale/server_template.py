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
:mod:`kingpin.actors.rightscale.server_template`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. _ServerTemplates_:
    http://reference.rightscale.com/api1.5/resources/ResourceServerTemplates.html
    http://reference.rightscale.com/api1.5/resources/ResourceServerTemplateMultiCloudImages.html
"""

import logging
import mock

from tornado import gen
import requests

from kingpin.actors import exceptions
from kingpin.actors.utils import dry
from kingpin.actors.rightscale import base
from kingpin.constants import SchemaCompareBase
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


class ServerTemplateMultiCloudImages(SchemaCompareBase):

    """Provides JSON-Schema based validation of the supplied Server Template.

    Each image is a dictionary that must have an MCI image name, and optionally
    whether or not its the default image for this template.

    _Note, only one MCI may have the is_default flag!_

    .. code-block:: json

        [
          {
              "mci": "Ubuntu 14.04 HVM".
              "rev": 5,
              "is_default": true,
          },
          {
              "mci": "Ubuntu 14.04 EBS".
          },
        ]
    }
    """

    SCHEMA = {
        'type': ['array', 'null'],
        'uniqueItems': True,
        'items': {
            'type': 'object',
            'required': ['mci'],
            'additionalProperties': False,
            'properties': {
                'mci': {
                    'type': 'string',
                    'minLength': 1,
                },
                'rev': {
                    'type': ['integer', 'string'],
                },
                'is_default': {
                    'type': 'boolean',
                },
            }
        }
    }


class ServerTemplate(base.EnsurableRightScaleBaseActor):

    """Manages the state of an RightScale ServerTemplate.

    This actor is able to create, destroy, modify and commit ServerTemplate
    revisions.

    Options match the documentation in RightScale:
    http://reference.rightscale.com/api1.5/resources/ResourceServerTemplates.html

    **Committing**

    If you wish to commit the template, set the `commit` option to the commit
    message you wish to use. If any change is made to the resource, Kingpin
    will commit a new revision with this message.

    **Options**

    :name:
      (str) The name of the template to be updated.

    :state:
      (str) Present or Absent. Default: "present"

    :commit:
      (str, None) If present, upon making changes to the HEAD version of the
      template, we will commit a new revision to RightScale. The provided
      string will be used as the commit message. Default: None

    :commit_head_dependencies:
      (bool) Commit all HEAD revisions (if any) of the associated MultiCloud
      Images, RightScripts and Chef repo sequences. Default: False

    :freeze_repositories:
      (bool) Freeze the repositories on commit. Default: False

    :tags:
      (list, str) A list of tags to add to the ServerTemplate.
      Default: None

    :description:
      (str) The description of the MCI image itself.
      Default: ""

    :images:
       A list of dicts that each describe a single cloud and the image in that
       cloud to launch. See below for details.

    **Image Definitions**

    Each cloud image definition is a dictionary that takes a few keys.

    :mci:
      (str) The name of the MultiCloudImage

    :rev:
      (str, int) The revision of the MultiCloudImage to use. Default: `0`

    :is_default:
      (bool) Whether or not this is the default MultiCloudImage for the
      template.

    **Examples**

    .. code-block:: json

        { "actor": "rightscale.ServerTemplate",
          "options": {
              "name": "Linux Server",
              "description": "this is a simple linux host",
              "images": [
                {
                    "mci": "Ubuntu 14.04 HVM",
                    "rev": 5,
                    "is_default": true,
                },
                {
                    "mci": "Ubuntu 14.04 EBS",
                }
              ]
          }
        }

    """

    all_options = {
        'name': (str, REQUIRED, 'The name of the template to be updated'),
        'commit': (str, None, 'Commit a new revision if changes made'),
        'commit_head_dependencies': (bool, False, (
            'Commit all HEAD revisions (if any) of the associated MultiCloud'
            'Images, RightScripts and Chef repo sequences.')
        ),
        'freeze_repositories': (bool, False,
                                'Freeze the repositories on commit'),
        'description': (str, None, 'The description of the to be updated'),
        'tags': ((list, str), None, 'List of tags to apply to the template'),
        'images': (ServerTemplateMultiCloudImages, None, (
            'A list of dicts that include our MultiCloudImage names'
            ', revisions (or default is HEAD), and optionally a '
            'is_default flag')),
    }

    unmanaged_options = [
        'commit', 'commit_head_dependencies', 'freeze_repositories', 'name'
    ]

    desc = 'RightScale ServerTemplate {name}'

    def __init__(self, *args, **kwargs):
        """Validate the user-supplied parameters at instantiation time."""

        super(ServerTemplate, self).__init__(*args, **kwargs)
        self.changed = False

        self.params = self._generate_rightscale_params(
            prefix='server_template',
            params={
                'description': self.option('description'),
                'name': self.option('name')
            })

        self._verify_one_default_image()

    def _verify_one_default_image(self):
        """Parses through the supplied images and finds the default one.

        If there are more than one default image defined, throws an exception.

        args:
            images: ServerTemplateMultiCloudImages object
        """
        default_image = [
            i['mci'] for i in self.option('images') if i.get('is_default')]

        if len(default_image) > 1:
            raise exceptions.InvalidOptions(
                'Only one image may have is_default set: %s' %
                ', '.join(default_image))

    @gen.coroutine
    def _precache(self):
        self.log.debug('Searching for ServerTemplate')
        st = yield self._client.find_by_name_and_keys(
            collection=self._client._client.server_templates,
            name=self.option('name'),
            revision=0)

        # Default searches return us an empty list if there are no matching
        # resources, or return us the exact resource we're looking for. Thus,
        # if the return value is not a list, then we know we got the
        # ServerTemplate back.
        if not isinstance(st, list):
            self.st = st

        # Build up our MCI "references" ... that is, take the plain text names
        # that the user submitted and turn them into proper HREFs and store
        # that as the desired "MCI References" state.
        #
        #  This dictionary ends up looking like this:
        #
        #  {
        #    "/api/multi_cloud_images/414637003": {
        #      "default": True,
        #    },
        #    "/api/multi_cloud_images/414123004": {
        #      "default": False,
        #    }
        #  }
        self.desired_images = {}
        tasks = []
        for image in self.option('images'):
            tasks.append(self._get_mci_href(image))
        yield tasks

        # If we got a list back, return None because that means that the
        # ServerTemplate doesn't already exist.
        if isinstance(st, list) and len(st) == 0:
            self.st = mock.MagicMock(name='<mocked template>')
            self.st.href = None
            self.st.soul = {
                'name': None,
                'description': None,
            }

            self.tags = []
            self.images = {}
            raise gen.Return()

        # Get the list of tags associated with the existing ST
        self.tags = (yield self._get_resource_tags(self.st))

        # Get the _live_ images associated with the server template
        # {
        #   "/api/multi_cloud_images/414637003": {
        #     "default": True,
        #     "map_href": "/api/server_template_multi_cloud_images/1234",
        #     "map_obj": <object itself for possible deletion>
        #   }
        # }
        self.images = yield self._get_mci_mappings()

    @gen.coroutine
    def _get_mci_href(self, image):
        name = image['mci']
        revision = image.get('revision', 0)
        default = image.get('is_default', False)

        mci = yield self._client.find_by_name_and_keys(
            collection=self._client._client.multi_cloud_images,
            name=name, revision=revision)

        if not mci:
            raise exceptions.InvalidOptions(
                'Invalid MCI Name/Rev supplied: %s/%s' % (name, revision))

        self.desired_images[mci.href] = {
            'default': default,
        }
        self.log.debug('Discovered %s (%s) -> %s' % (name, revision, mci.href))

    @gen.coroutine
    def _get_mci_mappings(self):
        if not self.st.href:
            raise gen.Return()

        raw = yield self._client.find_by_name_and_keys(
            collection=self._client._client.server_template_multi_cloud_images,
            server_template_href=self.st.href)
        if not isinstance(raw, list):
            raw = [raw]

        images = {}
        for mci_map in raw:
            self.log.debug('Existing MCI Mapping -> %s (default: %s)' %
                           (mci_map.href, mci_map.soul['is_default']))
            images[mci_map.links['multi_cloud_image']] = {
                'default': mci_map.soul['is_default'],
                'map_href': mci_map.href,
                'map_obj': mci_map
            }

        raise gen.Return(images)

    @gen.coroutine
    def _get_state(self):
        if not self.st or self.st.href is None:
            raise gen.Return('absent')

        raise gen.Return('present')

    @gen.coroutine
    def _set_state(self):
        if self.option('state') == 'absent':
            yield self._delete_st()
        else:
            yield self._create_st()

    @gen.coroutine
    @dry('Would have created the ServerTemplate')
    def _create_st(self):
        self.log.info('Creating ServerTemplate')
        self.st = yield self._client.create_resource(
            self._client._client.server_templates, self.params)
        self.changed = True

    @gen.coroutine
    @dry('Would have deleted ServerTemplate')
    def _delete_st(self):
        self.log.info('Deleting ServerTemplate')
        yield self._client.destroy_resource(self.st)
        self.changed = True

    @gen.coroutine
    def _get_description(self):
        raise gen.Return(self.st.soul['description'])

    @gen.coroutine
    @dry('Would have updated the template description')
    def _set_description(self):
        desc = self.option('description')
        self.log.info('Updating description: %s' % desc)
        self.st = yield self._client.update(self.st, self.params)
        self.changed = True

    @gen.coroutine
    def _get_tags(self):
        raise gen.Return(self.tags)

    @gen.coroutine
    def _set_tags(self):
        existing_tags = yield self._get_tags()
        new_tags = self.option('tags')

        # What tags should we add, delete?
        to_add = list(set(new_tags) - set(existing_tags))
        to_delete = list(set(existing_tags) - set(new_tags))

        if to_add:
            yield self._add_resource_tags(resource=self.st, tags=to_add)
            self.changed = True
        if to_delete:
            yield self._delete_resource_tags(resource=self.st, tags=to_delete)
            self.changed = True

    @gen.coroutine
    def _get_images(self):
        # Note, this method is never used.. just a placeholder. See
        # _compare_images() below instead.
        raise gen.Return()

    @gen.coroutine
    def _compare_images(self):
        # Copy the self.images dict, and then strip each key of the
        # map_href param. At this point, it should look identical to
        # our self.desired_images dict.
        existing_images = {}
        for image in self.images.keys():
            existing_images[image] = {
                'default': self.images[image]['default']
            }

        raise gen.Return(existing_images == self.desired_images)

    @gen.coroutine
    def _set_images(self):
        to_add = [href for href in self.desired_images.keys()
                  if href not in self.images.keys()]
        to_delete = [href for href in self.images.keys()
                     if href not in self.desired_images.keys()]

        tasks = []
        for href in to_add:
            tasks.append(self._create_mci_reference(href))
        yield tasks

        yield self._ensure_mci_default()

        tasks = []
        for href in to_delete:
            tasks.append(self._delete_mci_reference(
                self.images[href]['map_obj']))
        yield tasks

    @gen.coroutine
    @dry('Would have added MCI Mapping -> {0}')
    def _create_mci_reference(self, href):
        definition = self._generate_rightscale_params(
            prefix='server_template_multi_cloud_image',
            params={
                'multi_cloud_image_href': href,
                'server_template_href': self.st.href,
            }
        )

        self.log.info('Adding MCI %s to ServerTemplate' % href)
        yield self._client.create_resource(
            self._client._client.server_template_multi_cloud_images,
            definition)
        self.changed = True

    @gen.coroutine
    @dry('Would have deleted MCI reference {0.links[multi_cloud_image]}')
    def _delete_mci_reference(self, map_obj):
        self.log.info('Deleting MCI %s from ServerTemplate' %
                      map_obj.links['multi_cloud_image'])

        try:
            yield self._client.destroy_resource(map_obj)
        except requests.exceptions.HTTPError as e:
            if 'Default ServerTemplateMultiCloudImages' in e.response.text:
                raise exceptions.InvalidOptions(
                    'Cannot delete the current default MultiCloudImage '
                    'for this ServerTemplate. You must first re-assign a '
                    'new default image.')
        self.changed = True

    @gen.coroutine
    def _ensure_mci_default(self):
        """Sets the ServerTemplates Default MCI.

        After we've attached all of the MCIs to a ServerTemplate, we need to
        (optionally) set the "default" MCI to use if the user doesn't select
        one. This default can only be set after these attachments are made.
        Also, the default choice is then un-deletable from the MCI until a new
        default is selected.
        """
        # If there is no current default, then that means there are no MCIs
        # associated at all and we can't do anything. This only happens when
        # you're creating a new MCI from scratch.
        if 'default_multi_cloud_image' not in self.st.links:
            raise gen.Return()

        # Get the default MCI href as described by the user -- or just get the
        # first key in the list and treat that as the desired default.
        try:
            default_mci_href = [key for key in self.desired_images.keys()
                                if self.desired_images[key]['default'] is
                                True][0]
        except IndexError:
            default_mci_href = self.desired_images.keys()[0]

        # Compare the desired vs current default_multi_cloud_image_href. This
        # comparison is quick and doesn't require any API calls, so we do it
        # before we do anything else.
        current_default = self.st.links['default_multi_cloud_image']
        self.log.debug('Desired Default MCI HREF: %s' % default_mci_href)
        self.log.debug('Current Default MCI HREF: %s' % current_default)
        matching = (current_default == default_mci_href)

        # They match? Great, get out of here before we do anything bad!
        if matching:
            self.log.debug('Existing Default MCI HREF matches')
            raise gen.Return()

        # At this point, we know they don't match .. so we need to go off and
        # get all of the ServerTemplateMultiCloudImage references that link
        # these ServerTemplates to the MCIs.
        mci_refs = yield self._client.find_by_name_and_keys(
            collection=self._client._client.server_template_multi_cloud_images,
            server_template_href=self.st.href)

        # Final sanity check here -- if we're in DRY mode, get out!
        if self._dry:
            self.log.warning('Would have updated default MCI HREF to: %s'
                             % default_mci_href)
            raise gen.Return()

        # If we're not in DRY mode, AND we're updating the MCI reference to a
        # new default, then find the appropriate
        # server_template_muilti_cloud_image reference object. This should
        # always work, but some slowness in RightScales APIs has demonstrated
        # problems in the past, so we wrap this in a Try/Except block.
        try:
            new_default = [
                s for s in mci_refs
                if s.links['multi_cloud_image'] == default_mci_href][0]
        except IndexError:
            raise exceptions.InvalidOptions(
                'Unable to find the desired MultiCloud image '
                'attached to the ServerTemplate. This should never '
                'happen -- but can happen if the RightScale API is '
                'returning stale data. In that case, please wait and try '
                'again in the future.')

        # Finally, we have the desired new_default object... grab its URL
        # reference and lets make the API call.
        self.log.info('Making %s the default MCI' % default_mci_href)
        url = '%s/make_default' % new_default.links['self']
        yield self._client.make_generic_request(url, post=[])
        self.changed = True

    @gen.coroutine
    @dry('Would have committed HEAD to a revision')
    def _commit(self):
        self.log.info('Committing a new revision')
        params = {
            'commit_message': self.option('commit'),
            'freeze_repositories':
                str(self.option('freeze_repositories')).lower(),
            'commit_head_dependencies':
                str(self.option('commit_head_dependencies')).lower(),
        }

        ret = yield self._client.commit_resource(
            res=self.st,
            res_type=self._client._client.server_templates,
            params=params)

        self.log.info('Committed revision %s' % ret.soul['revision'])

    @gen.coroutine
    def _execute(self):
        yield super(ServerTemplate, self)._execute()

        # If we're deleting the MCI, then there is no need to continue after
        # we've done that.
        if self.option('state') == 'absent':
            raise gen.Return()

        # Finally, if we're committing and a change was made, commit!
        if self.changed and self.option('commit'):
            yield self._commit()
