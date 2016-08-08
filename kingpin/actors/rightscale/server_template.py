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
from kingpin.constants import STATE

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


class ServerTemplateBaseActor(base.RightScaleBaseActor):

    """Abstract ServerTemplate Actor that provides some utility methods."""

    def __init__(self, *args, **kwargs):
        """Validate the user-supplied parameters at instantiation time."""

        super(ServerTemplateBaseActor, self).__init__(*args, **kwargs)

        # Self.changed will be set to True if any _change_ occurs to an
        # ServerTemplate while its being managed. This is later leveraged by
        # the 'commit' option.
        self.changed = False

    @gen.coroutine
    def _get_st(self, name):
        """Searches RightScale for an ServerTemplate by name.

        Wrapper around our find_by_name_and_keys() mechanism so that we return
        either the proper ServerTemplate, or None if one isn't found.

        args:
            name: ServerTemplate name to search for
        """
        self.log.debug('Searching for ServerTemplate')
        st = yield self._client.find_by_name_and_keys(
            collection=self._client._client.server_templates,
            name=name,
            revision=0)

        # Default searches return us an empty list if there are no matching
        # resources, or return us the exact resource we're looking for. Thus,
        # if the return value is not a list, then we know we got the
        # ServerTemplate back.
        if not isinstance(st, list):
            raise gen.Return(st)

        # If we got a list back, return None because that means that the
        # ServerTemplate doesn't already exist.
        if isinstance(st, list) and len(st) == 0:
            raise gen.Return(None)

        # On anything else, raise an exception. Something really strange
        # happened.
        raise exceptions.RecoverableActorFailure(
            'Found too many matching ServerTemplates with the same name, '
            'this shouldn\'t be possible ... so something bad has happened.')

    @gen.coroutine
    def _create_st(self, name, params):
        """Creates a RightScale ServerTemplate if it doesn't exist.

        See http://reference.rightscale.com/api1.5/
            resources/ResourceServerTemplates.html#create

        Note, returns a mocked out ServerTemplate object if we're in a DRY run.
        This allows the rest of the actors to pretend like an ServerTemplate
        was created and continue with their checks.

        args:
            name: The name of the ServerTemplate we're creating
            params: RightScale-compatible list of tuples with the required
                    parameters defined in the URL above.

        returns:
            <rightscale.server_templates> object
        """
        st = yield self._get_st(name)
        if st:
            raise gen.Return(st)

        # If we're in a dry run, we return back a mocked out ServerTemplate
        # image object because its passed around a bunch for the other methods.
        if self._dry:
            self.log.warning('Would have created ServerTemplate')

            st = mock.MagicMock(name=name)
            st.href = None
            st.soul = {
                'name': '<mocked st %s>' % name,
                'description': None
            }
            raise gen.Return(st)

        self.log.info('Creating ServerTemplate')
        st = yield self._client.create_resource(
            self._client._client.server_templates, params)
        self.changed = True
        raise gen.Return(st)

    @gen.coroutine
    @dry('Would have deleted ServerTemplate: {name}')
    def _delete_st(self, name):
        """Deletes a RightScale ServerTemplate if it exists.

        See http://reference.rightscale.com/api1.5/
            resources/ResourceServerTemplates.html#destroy

        args:
            name: The name of the ServerTemplate we're destroying
        """
        st = yield self._get_st(name)
        if not st:
            raise gen.Return()

        self.log.info('Deleting ServerTemplate')
        yield self._client.destroy_resource(st)
        self.changed = True

    @gen.coroutine
    def _get_st_mci_refs(self, image, server_template):
        """Returns a fully populated set of ServerTemplate MCI References.

        See http://reference.rightscale.com/api1.5/
        resources/ResourceServerTemplateMultiCloudImages.html for details.

        This method takes in a dictionary with as set of parameters (mci,
        rev) and returns a fully ready-to-use set of RightScale-formatted
        parameters to update that image. The method handles discovering the
        RightScale HREFs.

        Args:
            image: A dictionary with the keys: mci, rev
            server_template: A RightScale.server_templates object

        Returns:
            A tuple with two keys:
              (<a list of RightScale-formatted array of tuples>,
               <Boolean whether or not this is the desired default MCI>)
        """
        name = image['mci']
        rev = image.get('rev', 0)

        mci = yield self._client.find_by_name_and_keys(
            collection=self._client._client.multi_cloud_images,
            name=name, revision=rev)

        if not mci:
            raise exceptions.InvalidOptions(
                'Invalid MCI Name/Rev supplied: %s/%s' % (name, rev))

        definition = self._generate_rightscale_params(
            prefix='server_template_multi_cloud_image',
            params={
                'multi_cloud_image_href': mci.href,
                'server_template_href': server_template.href,
            }
        )

        self.log.debug('Prepared template MCI reference: %s' % definition)

        ret = (definition, image.get('is_default', False))

        raise gen.Return(ret)

    @gen.coroutine
    @dry('Would have added {mci_ref_param[0][1]}')
    def _create_st_mci_reference(self, mci_ref_param):
        self.log.info('Adding MCI %s to ServerTemplate' % mci_ref_param[0][1])
        yield self._client.create_resource(
            self._client._client.server_template_multi_cloud_images,
            mci_ref_param)
        self.changed = True

    @gen.coroutine
    @dry('Would have deleted {mci_ref_obj.links[multi_cloud_image]}')
    def _delete_st_mci_reference(self, mci_ref_obj):
        self.log.info('Deleting MCI %s from ServerTemplate'
                      % mci_ref_obj.links['multi_cloud_image'])

        try:
            yield self._client.destroy_resource(mci_ref_obj)
        except requests.exceptions.HTTPError as e:
            if 'Default ServerTemplateMultiCloudImages' in e.response.text:
                raise exceptions.InvalidOptions(
                    'Cannot delete the current default MultiCloudImage '
                    'for this ServerTemplate. You must first re-assign a '
                    'new default image.')
        self.changed = True

    @gen.coroutine
    @dry('Would have updated the template description to: {description}')
    def _update_description(self, st, description, params):
        self.log.info('Updating MCI description: %s' % description)
        st = yield self._client.update(st, params)
        self.changed = True
        raise gen.Return(st)


class ServerTemplate(ServerTemplateBaseActor):

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
        'state': (STATE, 'present',
                  'Desired state of the image: present/absent'),
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

    desc = 'RightScale ServerTemplate {name}'

    def __init__(self, *args, **kwargs):
        """Validate the user-supplied parameters at instantiation time."""

        super(ServerTemplate, self).__init__(*args, **kwargs)
        self.changed = False

        self._st_params = self._generate_rightscale_params(
            prefix='server_template',
            params={
                'description': self.option('description'),
                'name': self.option('name')
            })

        self._verify_one_default_image(self.option('images'))

    def _verify_one_default_image(self, images):
        """Parses through the supplied images and finds the default one.

        If there are more than one default image defined, throws an exception.

        args:
            images: ServerTemplateMultiCloudImages object
        """
        default_image = [
            i['mci'] for i in images if i.get('is_default')]

        if len(default_image) > 1:
            raise exceptions.InvalidOptions(
                'Only one image may have is_default set: %s' %
                ', '.join(default_image))

    @gen.coroutine
    def _ensure_st(self):
        state = self.option('state')
        name = self.option('name')
        self.log.info('Ensuring that template is %s' % state)
        st = yield self._get_st(name)

        if state == 'absent' and st is None:
            self.log.debug('ServerTemplate does not exist')
        elif state == 'absent' and st:
            yield self._delete_st(name=name)
            st = None
        elif state == 'present' and st is None:
            st = yield self._create_st(name=name,
                                       params=self._st_params)
        elif state == 'present' and st:
            self.log.debug('ServerTemplate exists')

        raise gen.Return(st)

    @gen.coroutine
    def _ensure_description(self, st):
        existing = st.soul['description']
        new = self.option('description')

        if existing == new:
            self.log.debug('Descriptions match')
            raise gen.Return()

        yield self._update_description(
            st, description=new, params=self._st_params)

    @gen.coroutine
    def _ensure_st_mci_default(self, st, default_mci_href):
        """Sets the ServerTemplates Default MCI.

        After we've attached all of the MCIs to a ServerTemplate, we need to
        (optionally) set the "default" MCI to use if the user doesn't select
        one. This default can only be set after these attachments are made.
        Also, the default choice is then un-deletable from the MCI until a new
        default is selected.

        This method takes in the ServerTemplate object (st) as well as the
        desired MCI HREF (default_mci_href). It makes an additional API call to
        get the ServerTemplate Multi Cloud IMages that are attached. Once it
        has all of that information, if does some comparisons and makes the
        appropriate changes if necessary,

        args:
            st: <rightscale.server_templates> object
            default_mci_href: A string with the desired MCI HREF
        """
        # If there is no current default, then that means there are no MCIs
        # associated at all and we can't do anything. This only happens when
        # you're creating a new MCI from scratch.
        if 'default_multi_cloud_image' not in st.links or not default_mci_href:
            raise gen.Return()

        # Compare the desired vs current default_multi_cloud_image_href. This
        # comparison is quick and doesn't require any API calls, so we do it
        # before we do anything else.
        current_default = st.links['default_multi_cloud_image']
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
            server_template_href=st.links['self'])

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

    """Ensures what MCIs are linked to a given Server Template.

    ServerTemplates hold references called ServerTemplateMulti
    CloudImages to MCIs. This method walks through the mappings
    and creates/deletes/updates them as necessary.

    args:
        st: Server Template object that we're working with
    """
    @gen.coroutine
    def _ensure_st_mcis(self, st):
        # If the server template is mocked out, then don't run this
        if not st.href:
            raise gen.Return()

        # Get the existing MCI cloud settings
        existing = yield self._client.find_by_name_and_keys(
            collection=self._client._client.server_template_multi_cloud_images,
            server_template_href=st.links['self'])
        if not isinstance(existing, list):
            existing = [existing]

        # Go off and generate what the new settings should look like -- this is
        # an async IO operation because we let the users give us sane
        # human-readable resource names, and then we go and discover their raw
        # HREFs in the RightScale API.
        tasks = []
        for image in self.option('images'):
            tasks.append(self._get_st_mci_refs(image, st))
        new = yield tasks

        # First, lets create-or-update anything thats not in the
        # existing list of configured settings.
        tasks = []
        for (param, is_default) in new:
            # Get thew MCI HREF path for comparison purposes below
            new_mci_href = [
                s[1] for s in param if 'multi_cloud_image_href' in s[0]][0]

            # Dig through the existing MCI HREF list and look for ones that
            # match the HREF we just got above. If nothing is returned, then we
            # know we need to add this HREF to the Server Template.
            existing_mci = [
                s for s in existing
                if s.links['multi_cloud_image'] == new_mci_href]

            # If the configured image doesn't exist in our existing list of
            # cloud images, then lets just create it.
            if len(existing_mci) == 0:
                tasks.append(self._create_st_mci_reference(
                    mci_ref_param=param))
                continue
        yield tasks

        for (param, is_default) in new:
            new_mci_href = [
                s[1] for s in param if 'multi_cloud_image_href' in s[0]][0]
            if is_default:
                yield self._ensure_st_mci_default(st, new_mci_href)

        # Now that we've added or updated the cloud images we _want_, lets
        # purge any that are no longer listed.
        tasks = []
        for obj in existing:

            # This could be done in a one liner, but its really hard to read.
            # We're digging through the list of tuples (new), and then digging
            # into the first element of that tuple (param), and finally pulling
            # out the value for the multi_cloud_image_href.
            new_cloud_hrefs = []
            for (param, is_default) in new:
                param = dict(param)
                new_cloud_hrefs.append(
                    param[('server_template_multi_cloud_image'
                           '[multi_cloud_image_href]')])

            # Once we have the list of new multi_coud_image_hrefs that we want
            # to be attached to the template, we search for any that ARE
            # attached, but ARE NOT in the list. We then delete those.
            if obj.links['multi_cloud_image'] not in new_cloud_hrefs:
                tasks.append(self._delete_st_mci_reference(mci_ref_obj=obj))

        yield tasks

    @gen.coroutine
    @dry('Would have committed HEAD to a revision')
    def _commit(self, st, message):
        self.log.info('Committing a new revision')
        params = {
            'freeze_repositories':
                str(self.option('freeze_repositories')).lower(),
            'commit_head_dependencies':
                str(self.option('commit_head_dependencies')).lower(),
        }

        ret = yield self._client.commit_resource(
            res=st,
            res_type=self._client._client.server_templates,
            message=message,
            params=params)

        self.log.info('Committed revision %s' % ret.soul['revision'])

    @gen.coroutine
    def _execute(self):

        st = yield self._ensure_st()

        # If we're deleting the MCI, then there is no need to continue after
        # we've done that.
        if self.option('state') == 'absent':
            raise gen.Return()

        # Ensure that the description is up to date
        yield self._ensure_description(st)

        # If tags were supplied, then manage them.
        if self.option('tags'):
            yield self._ensure_tags(st, self.option('tags'))

        # Ensure that all of the configured images themselves match
        yield self._ensure_st_mcis(st)

        # Finally, if we're committing and a change was made, commit!
        if self.changed and self.option('commit'):
            yield self._commit(st, self.option('commit'))
