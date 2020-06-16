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
:mod:`kingpin.actors.rightscale.mci`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. _MultiCloudImages_:
    http://reference.rightscale.com/api1.5/resources/ResourceMultiCloudImages.html
    http://reference.rightscale.com/api1.5/resources/ResourceMultiCloudImageSettings.html
"""

import logging
import mock

from tornado import gen

from kingpin.actors import exceptions
from kingpin.actors.utils import dry
from kingpin.actors.rightscale import base
from kingpin.constants import SchemaCompareBase
from kingpin.constants import REQUIRED
from kingpin.constants import STATE

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


class MultiCloudImageSettings(SchemaCompareBase):

    """Provides JSON-Schema based validation of the supplied MultiCloudImage.

    Each image is a dictionary that must have a cloud, image, instance_type and
    optionally some user_data.

    .. code-block:: json

        [
          {
              "cloud": "EC2 us-west-2",
              "image": "ami-e29774d1",
              "instance_type": "m1.small",
              "user_data": "cd /bin/bash"
          },
          {
              "cloud": "EC2 us-west-1",
              "image": "ami-b58142f1",
              "instance_type": "m1.small",
              "user_data": "cd /bin/bash"
          }
        ]
    }
    """

    SCHEMA = {
        'type': ['array', 'null'],
        'uniqueItems': True,
        'items': {
            'type': 'object',
            'required': ['cloud', 'image', 'instance_type'],
            'additionalProperties': False,
            'properties': {
                'cloud': {
                    'type': 'string',
                    'minLength': 1,
                    'maxLength': 255,
                },
                'image': {
                    'type': 'string',
                },
                'instance_type': {
                    'type': 'string',
                },
                'user_data': {
                },
            }
        }
    }


class MCIBaseActor(base.RightScaleBaseActor):

    """Abstract MCI Actor that provides some utility methods."""

    def __init__(self, *args, **kwargs):
        """Validate the user-supplied parameters at instantiation time."""

        super(MCIBaseActor, self).__init__(*args, **kwargs)

        # Self.changed will be set to True if any _change_ occurs to an MCI
        # while its being managed. This is later leveraged by the 'commit'
        # option.
        self.changed = False

    @gen.coroutine
    def _get_mci(self, name):
        """Searches RightScale for an MCI by name.

        Wrapper around our find_by_name_and_keys() mechanism so that we return
        either the proper MCI, or None if one isn't found.

        args:
            name: MCI name to search for
        """
        self.log.debug('Searching for MCI "%s"' % name)
        mci = yield self._client.find_by_name_and_keys(
            collection=self._client._client.multi_cloud_images,
            name=name,
            revision=0)

        # Default searches return us an empty list if there are no matching
        # resources, or return us the exact resource we're looking for. Thus,
        # if the return value is not a list, then we know we got the MCI back.
        # got a list bac
        if not isinstance(mci, list):
            raise gen.Return(mci)

        # If we got a list back, return None because that means that the MCI
        # doesn't already exist.
        if isinstance(mci, list) and len(mci) == 0:
            raise gen.Return(None)

        # On anything else, raise an exception. Something really strange
        # happened.
        raise exceptions.RecoverableActorFailure(
            'Found too many matching MCI images with the same name, '
            'this shouldn\'t be possible ... so something bad has happened.')

    @gen.coroutine
    def _create_mci(self, name, params):
        """Creates a RightScale MCI if it doesn't exist.

        See http://reference.rightscale.com/api1.5/
            resources/ResourceMultiCloudImages.html#create

        Note, returns a mocked out MCI object if we're in a DRY run. This
        allows the rest of the actors to pretend like an MCI was created and
        continue with their checks.

        args:
            name: The name of the MCI we're creating
            params: RightScale-compatible list of tuples with the required
                    parameters defined in the URL above.

        returns:
            <rightscale.multi_cloud_image> object
        """
        mci = yield self._get_mci(name)
        if mci:
            raise gen.Return(mci)

        # If we're in a dry run, we return back a mocked out MCI image object
        # because its passed around a bunch for the other methods.
        if self._dry:
            self.log.warning('Would have created MCI: %s' % name)

            mci = mock.MagicMock(name=name)
            mci.href = None
            mci.soul = {
                'name': '<mocked MCI %s>' % name,
                'description': None
            }
            raise gen.Return(mci)

        self.log.info('Creating MCI %s' % self.option('name'))
        mci = yield self._client.create_resource(
            self._client._client.multi_cloud_images, params)
        self.changed = True
        raise gen.Return(mci)

    @gen.coroutine
    @dry('Would have deleted MCI: {name}')
    def _delete_mci(self, name):
        """Deletes a RightScale MCI if it exists.

        See http://reference.rightscale.com/api1.5/
            resources/ResourceMultiCloudImages.html#destroy

        args:
            name: The name of the MCI we're creating
        """
        mci = yield self._get_mci(name)
        if not mci:
            raise gen.Return()

        self.log.info('Deleting MCI %s' % name)
        yield self._client.destroy_resource(mci)
        self.changed = True

    @gen.coroutine
    def _get_mci_setting_def(self, settings):
        """Returns a fully populated set of Multi Cloud Image Settings.

        See http://reference.rightscale.com/api1.5/
        resources/ResourceMultiCloudImageSettings.html for details.

        This method takes in a dictionary with as set of parameters (cloud,
        image, instance_type, user_data) and returns a fully ready-to-use
        set of RightScale-formatted parameters to update that image. The method
        handles discovering the RightScale HREFs for the cloud, image and
        instance_type options.

        Args:
            settings: A dictionary with the keys: cloud, image,
            instance_type, user_data

        Returns:
            A RightScale-formatted array of tuples.
        """

        # Get our cloud object first -- its required so that we can search for
        # the image/ramdisk/etc hrefs.
        cloud = yield self._client.find_by_name_and_keys(
            collection=self._client._client.clouds,
            name=settings['cloud'])
        if not cloud:
            raise exceptions.InvalidOptions(
                'Invalid Cloud name supplied: %s' % settings['cloud'])

        # Find our image by searching for the resource_uid that matches.
        image = yield self._client.find_by_name_and_keys(
            collection=cloud.images,
            resource_uid=settings['image'])
        if not image:
            raise exceptions.InvalidOptions(
                'Invalid cloud image name supplied: %s' % settings['image'])

        # Find our instance type now too
        instance = yield self._client.find_by_name_and_keys(
            collection=cloud.instance_types,
            name=settings['instance_type'])
        if not instance:
            raise exceptions.InvalidOptions(
                'Invalid cloud instance_type supplied: %s' %
                settings['instance_type'])

        # Generate our mci parameters, and each of the image settings
        # parameters. This validates that our inputs are all correct one last
        # time.
        params = {'cloud_href': cloud.href,
                  'image_href': image.href,
                  'instance_type_href': instance.href,
                  }
        if settings.get('user_data'):
            params['user_data'] = settings['user_data']

        definition = self._generate_rightscale_params(
            prefix='multi_cloud_image_setting',
            params=params)

        self.log.debug('Prepared MCI Image Definition: %s' % definition)
        raise gen.Return(definition)

    @gen.coroutine
    @dry('Would have added {cloud} to {mci.soul[name]}')
    def _create_mci_setting(self, cloud, mci, params):
        self.log.info('Adding Cloud %s to MCI %s' % (cloud, mci.soul['name']))
        yield self._client.create_resource(mci.settings, params)
        self.changed = True

    @gen.coroutine
    @dry('Would have updated the {mci_setting.links[cloud]} image settings')
    def _update_mci_setting(self, mci_setting, params):
        self.log.info('Updating Cloud %s settings' %
                      mci_setting.links['cloud'])
        yield self._client.update(mci_setting, params)
        self.changed = True

    @gen.coroutine
    @dry('Would have deleted the {mci_setting.links[cloud]} image settings')
    def _delete_mci_setting(self, mci_setting):
        self.log.info('Deleting Cloud %s settings' %
                      mci_setting.links['cloud'])
        yield self._client.destroy_resource(mci_setting)
        self.changed = True

    @gen.coroutine
    @dry('Would have updated the MCI description to: {description}')
    def _update_description(self, mci, description, params):
        self.log.info('Updating MCI description: %s' % description)
        mci = yield self._client.update(mci, params)
        self.changed = True
        raise gen.Return(mci)

    def _diff_setting(self, mci_setting, new_params):
        """Compares MCI Cloud Image settings to the newly requested params.

        Takes in a rightscale.multi_cloud_image.settings object and converts it
        into a list of RightScale-compatible tuples. Then compares these tuples
        to the tuples we want the cloud image setting to have. If they match,
        returns True, otherwise False.

        Note, strips out the user_data that the user supplied from the
        new_params because the user_data cannot be pulled down from the API at
        this time.

        args:
            mci_setting: A rightscale.multi_cloud_image.settings object
            new_params: A list of RightScale API-compatble tuples that we are
            comparing against.

        returns:
            boolean
        """
        links = mci_setting.links
        existing_params = [
            ('multi_cloud_image_setting[image_href]', links['image']),
            # See note in _diff_setting() about why this is commented out
            # ('multi_cloud_image_setting[user_data]', data[...]),
            ('multi_cloud_image_setting[instance_type_href]',
             links['instance_type']),
            ('multi_cloud_image_setting[cloud_href]', links['cloud'])]

        # NOTE: the user_data cannot be diffed because RightScale does not
        # provide a way to get this back via their API. This sucks, but for the
        # purposes of this diff_setting() method, we explicitly strip out the
        # user_data and only diff the other settings.
        new_params = [
            (key, value) for key, value in new_params if key !=
            'multi_cloud_image_setting[user_data]']

        return set(existing_params) != set(new_params)


class MCI(MCIBaseActor):

    """Manages the state of an RightScale MultiCloudImage.

    This actor is able to create, destroy, modify and commit MultiCloudImage
    revisions.

    Options match the documentation in RightScale:
    http://reference.rightscale.com/api1.5/resources/ResourceMultiCloudImages.html

    **Committing**

    If you wish to commit the MCI, set the `commit` option to the commit
    message you wish to use. If any change is made to the resource, Kingpin
    will commit a new revision with this message.

    **Options**

    :name:
      (str) The name of the MCI to be updated.

    :state:
      (str) Present or Absent. Default: "present"

    :commit:
      (str, None) If present, upon making changes to the HEAD version of the
      MCI, we will commit a new revision to RightScale. The provided string
      will be used as the commit message. Default: None

    :tags:
      (list, str) A list of tags to add to the MultiCloud image.
      Default: None

    :description:
      (str) The description of the MCI image itself.
      Default: ""

    :images:
       A list of dicts that each describe a single cloud and the image in that
       cloud to launch. See below for details.

    **Image Definitions**

    Each cloud image definition is a dictionary that takes a few keys.

    :cloud:
      (str) The name of the cloud as found in RightScale. We use the cloud
      'Name' which can be found in your `Settings -> Account Settings -> Clouds
      -> insert_cloud_here` page. For example `AWS us-west-2`.

    :image:
      (str) The cloud-specific Image UID. For example `ami-a1234abc`.

    :instance_type:
      (str) The default instance type to launch when this AMI is launched. For
      example, `m1.small`.
      (*optional*)

    :user_data:
      (str) The custom user data to pass to the instance on-bootup.
      (*optional*)

    **Examples**

    .. code-block:: json

        { "actor": "rightscale.MCI",
          "options": {
              "name": "Ubuntu i386 14.04",
              "description": "this is our test mci",
              "images": [
                {
                    "cloud": "EC2 us-west-2",
                    "image": "ami-e29774d1",
                    "instance_type": "m1.small",
                    "user_data": "cd /bin/bash"
                },
                {
                    "cloud": "EC2 us-west-1",
                    "image": "ami-b58142f1",
                    "instance_type": "m1.small",
                    "user_data": "cd /bin/bash"
                }
              ]
          }
        }

    """

    all_options = {
        'name': (str, REQUIRED, 'The name of the MCI to be updated'),
        'state': (STATE, 'present',
                  'Desired state of the image: present/absent'),
        'commit': (str, None, 'Commit a new MCI revision if changes made'),
        'description': (str, None, 'The description of the MCI to be updated'),
        'tags': ((list, str), None, 'List of tags to apply to the MCI'),
        'images': (
            MultiCloudImageSettings, None,
            'A list of objects that describe our per cloud image settings'),
    }

    desc = 'RightScale MCI {name}'

    def __init__(self, *args, **kwargs):
        """Validate the user-supplied parameters at instantiation time."""

        super(MCI, self).__init__(*args, **kwargs)
        self.changed = False
        self._mci_params = self._generate_rightscale_params(
            prefix='multi_cloud_image',
            params={
                'description': self.option('description'),
                'name': self.option('name')
            })

    @gen.coroutine
    def _ensure_mci(self):
        state = self.option('state')
        name = self.option('name')
        self.log.info('Ensuring that MCI %s is %s' % (name, state))
        mci = yield self._get_mci(name)

        if state == 'absent' and mci is None:
            self.log.debug('MCI does not exist')
        elif state == 'absent' and mci:
            yield self._delete_mci(name=name)
            mci = None
        elif state == 'present' and mci is None:
            mci = yield self._create_mci(name=name,
                                         params=self._mci_params)
        elif state == 'present' and mci:
            self.log.debug('MCI exists')

        raise gen.Return(mci)

    @gen.coroutine
    def _ensure_description(self, mci):
        existing = mci.soul['description']
        new = self.option('description')

        if existing == new:
            self.log.debug('Descriptions match')
            raise gen.Return()

        yield self._update_description(
            mci, description=new, params=self._mci_params)

    @gen.coroutine
    @dry('Would have force-set the user_data')
    def _force_mci_setting_user_data(self, mci_setting, params):
        """Temporary method to forcefully set the user_data on an MCI.

        RightScale does not currently allow us to check what the existing
        user_data is for a given MCI Setting. For that reason, we have to
        forcefully reset this data every time the code runs to ensure that its
        as expected.

        We treat this as a separate method call because we hope to remove this
        in the future, and keeping it separate makes it eaiser to remove down
        the road. Additionally, this method does not trigger the self.changed
        boolean, so it does not cause a new committed revision of the MCI to be
        created on every run.

        Again, we hope to destroy this method soon!

        args:
            mci_setting: rightscale.multi_cloud_images.setting object
            params: The parameters to force-set for the MCI setting
        """
        self.log.info('Force-setting the user_data')
        try:
            yield self._client.update(mci_setting, params)
        except StopIteration:
            return

    @gen.coroutine
    def _ensure_settings(self, mci):
        # Get the existing MCI cloud settings
        existing = yield self._client.show(mci.settings)

        # Go off and generate what the new settings should look like -- this is
        # an async IO operation because we let the users give us sane
        # human-readable resource names, and then we go and discover their raw
        # HREFs in the RightScale API.
        tasks = []
        for image in self.option('images'):
            tasks.append(self._get_mci_setting_def(image))
        new = yield tasks

        # First, lets create-or-update anything thats not in the
        # existing list of configured settings.
        tasks = []
        for new_setting in new:
            # Dive into the list of tuples for this cloud image setting and
            # find its HREF.
            new_cloud_href = [
                s[1] for s in new_setting if 'cloud_href' in s[0]][0]

            # Dig through the existing settings list and look for settings
            # objects that match the cloud name of the new_setting dict. If
            # none are received, this is an empty list.. otherwise, it should
            # only have one item in it.
            existing_setting = [
                s for s in existing if s.links['cloud'] == new_cloud_href]

            # If the configured image doesn't exist in our existing list of
            # cloud images, then lets just create it.
            if len(existing_setting) == 0:
                tasks.append(self._create_mci_setting(
                    cloud=new_cloud_href,
                    mci=mci,
                    params=new_setting))
                continue

            # Now, if the cloud IS defined already in the MCi, then we have to
            # see if they match .. or if they don't, we'll have to update them.
            #
            # Note, it should be impossible according to RightScale for this to
            # be > 1 ... you cannot have multiple cloud images for the same
            # cloud href, so we only need to think about the scenario where
            # this is == 1.
            if len(existing_setting) == 1:
                if self._diff_setting(existing_setting[0], new_setting):
                    tasks.append(self._update_mci_setting(
                        mci_setting=existing_setting[0],
                        params=new_setting))

                # Temporary -- when rightscale lets us check the user_data
                # value via the api, we won't have to do this anymore.
                tasks.append(self._force_mci_setting_user_data(
                    mci_setting=existing_setting[0],
                    params=new_setting))

        # Now that we've added or updated the cloud images we _want_, lets
        # purge any that are no longer listed.
        for existing_setting in existing:
            existing_cloud_href = existing_setting.links['cloud']
            new_cloud_hrefs = [
                dict(s)['multi_cloud_image_setting[cloud_href]'] for s in new]

            if existing_cloud_href not in new_cloud_hrefs:
                tasks.append(self._delete_mci_setting(
                    mci_setting=existing_setting))

        yield tasks

    @gen.coroutine
    @dry('Would have committed HEAD to a revision')
    def _commit(self, mci, message):
        self.log.info('Committing a new revision')
        ret = yield self._client.commit_resource(
            res=mci,
            res_type=self._client._client.multi_cloud_images,
            message=message)
        self.log.info('Committed revision %s' % ret.soul['revision'])

    @gen.coroutine
    def _execute(self):

        mci = yield self._ensure_mci()

        # If we're deleting the MCI, then there is no need to continue after
        # we've done that.
        if self.option('state') == 'absent':
            raise gen.Return()

        # Ensure that the description is up to date
        yield self._ensure_description(mci)

        # If tags were supplied, then manage them.
        if self.option('tags'):
            yield self._ensure_tags(mci, self.option('tags'))

        # Ensure that all of the configured images themselves match
        yield self._ensure_settings(mci)

        # Finally, if we're committing and a change was made, commit!
        if self.changed and self.option('commit'):
            yield self._commit(mci, self.option('commit'))
