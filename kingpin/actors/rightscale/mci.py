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
:mod:`kingpin.actors.rightscale.mci`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. _MultiCloudImages_:
    http://reference.rightscale.com/api1.5/resources/ResourceMultiCloudImages.html
    http://reference.rightscale.com/api1.5/resources/ResourceMultiCloudImageSettings.html
"""

import logging

from tornado import gen

from kingpin.actors import exceptions
from kingpin.actors.rightscale import base
from kingpin.constants import REQUIRED

log = logging.getLogger(__name__)

__author__ = 'Matt Wise <matt@nextdoor.com>'


class MCIBaseActor(base.RightScaleBaseActor):

    """Abstract MCI Actor that provides some utility methods."""


class Create(MCIBaseActor):

    """Creates a RightScale Multi Cloud Image.

    Options match the documentation in RightScale:
    http://reference.rightscale.com/api1.5/resources/ResourceMultiCloudImages.html

    **Options**

    :name:
      The name of the MCI to be created.

    :description:
       The description of the MCI to be created.
       (*optional*)

    :images:
       A list of dicts that each describe a single cloud and the image in that
       cloud to launch. See below for details.

    **Image Definitions**

    Each cloud image definition is a dictionary that takes a few keys.

    :cloud:
      The name of the cloud as found in RightScale. We use the cloud 'Name'
      which can be found in your `Settings -> Account Settings -> Clouds ->
      insert_cloud_here` page. For example `AWS us-west-2`.

    :image:
      The cloud-specific Image UID. For example `ami-a1234abc`.

    :instance_type:
      The default instance type to launch when this AMI is launched. For
      example, `m1.small`.
      (*optional*)

    :user_data:
      The custom user data to pass to the instance on-bootup.
      (*optional*)

    **Examples**

    .. code-block:: json

        { "actor": "rightscale.mci.Create",
          "desc": "Create an MCI",
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
        'name': (str, REQUIRED, 'The name of the MCI to be created.'),
        'description': (
            str, '',
            'The description of the MCI to be created.'),
        'images': (
            list, [],
            'A list of objects that describe our per cloud image settings.'),
    }

    def __init__(self, *args, **kwargs):
        """Validate the user-supplied parameters at instantiation time."""

        super(Create, self).__init__(*args, **kwargs)

        allowed_image_options = (
            'cloud', 'image', 'instance_type', 'user_data')
        required_image_options = ('cloud', 'image')

        for image in self.option('images'):
            # Sanity check that no extra options were passed in
            for key in image.keys():
                if key not in allowed_image_options:
                    raise exceptions.InvalidOptions(
                        'Invalid option (%s) found in Image %s' % (key, image))

            # Make sure that the required options were passed in
            for required in required_image_options:
                if required not in image.keys():
                    raise exceptions.InvalidOptions(
                        'Missing option "%s" in Image %s' %
                        (required, image))

    @gen.coroutine
    def _get_image_def(self, description):
        """Returns a fully populated set of Multi Cloud Image settings.

        This method takes in a dictionary with as set of parameters (cloud,
        image, instance_type, user_data) and returns a fully ready-to-use
        set of RightScale-formatted parameters to create that image. The method
        handles discovering the RightScale HREFs for the cloud, image and
        instance_type options.

        Args:
            description: A dictionary with the keys: cloud, image,
            instance_type, user_data

        Returns:
            A RightScale-formatted array of tuples.
        """

        # Get our cloud object first -- its required so that we can search for
        # the image/ramdisk/etc hrefs.
        cloud = yield self._client.find_by_name_and_keys(
            collection=self._client._client.clouds,
            name=description['cloud'])
        if not cloud:
            raise exceptions.InvalidOptions(
                'Invalid Cloud name supplied: %s' % description['cloud'])

        # Find our image by searching for the resource_uid that matches.
        image = yield self._client.find_by_name_and_keys(
            collection=cloud.images,
            resource_uid=description['image'])
        if not image:
            raise exceptions.InvalidOptions(
                'Invalid cloud image name supplied: %s' % description['image'])

        # Find our instance type now too
        instance = yield self._client.find_by_name_and_keys(
            collection=cloud.instance_types,
            name=description['instance_type'])
        if not instance:
            raise exceptions.InvalidOptions(
                'Invalid cloud instance_type supplied: %s' %
                description['instance_type'])

        # Generate our mci parameters, and each of the image settings
        # parameters. This validates that our inputs are all correct one last
        # time.
        definition = self._generate_rightscale_params(
            prefix='multi_cloud_image_setting',
            params={
                'cloud_href': cloud.href,
                'image_href': image.href,
                'instance_type_href': instance.href,
                'user_data': description['user_data'],
            })

        self.log.debug('Prepared MCI Image Definition: %s' % definition)
        raise gen.Return(definition)

    @gen.coroutine
    def _execute(self):

        # Make sure the MCI doesn't already exist. If it does, we bail.
        mci = yield self._client.find_by_name_and_keys(
            collection=self._client._client.multi_cloud_images,
            name=self.option('name'))
        if mci:
            raise exceptions.InvalidOptions(
                'MCI "%s" already exists.' % self.option('name'))

        # Generate the parameters for creating the top level MCI object
        mci_params = self._generate_rightscale_params(
            prefix='multi_cloud_image',
            params={
                'description': self.option('description'),
                'name': self.option('name')
            })

        # Now, we need to validate that all of the inputs are correct by
        # discovering the hrefs for each of the images supplied.
        image_futures = []
        for image in self.option('images'):
            image_futures.append(self._get_image_def(image))
        mci_settings_params = yield image_futures

        # Finally, if we're dry, bail out..
        if self._dry:
            self.log.info('Would have created MCI: %s' % self.option('name'))
            for setting in mci_settings_params:
                self.log.info('Image Def: %s' % setting)
            raise gen.Return()

        # Ok, lets create this thing!
        self.log.info('Creating MCI %s' % self.option('name'))
        mci = yield self._client.create_resource(
            self._client._client.multi_cloud_images, mci_params)

        # Now add each of the image descriptions to the mci
        for setting in mci_settings_params:
            self.log.info('Creating MCI Setting: %s' % setting)
            yield self._client.create_resource(
                mci.settings, setting)


class Destroy(MCIBaseActor):

    """Deletes a RightScale MCI.

    Options match the documentation in RightScale:
    http://reference.rightscale.com/api1.5/resources/ResourceMultiCloudImages.html

    **Options**

    :name:
      The name of the multi cloud image to be deleted.

    **Examples**

    .. code-block:: json

        { "actor": "rightscale.mci.Destroy",
          "desc": "Create an MCI",
          "options": {
              "name": "Ubuntu i386 14.04",
          }
        }

    """

    all_options = {
        'name': (str, REQUIRED,
                 'The name of the multi cloud image to be deleted.'),
    }

    @gen.coroutine
    def _execute(self):

        mci = yield self._client.find_by_name_and_keys(
            collection=self._client._client.multi_cloud_images,
            name=self.option('name'))
        if not mci:
            raise exceptions.InvalidOptions(
                'MCI "%s" does not exist.' % self.option('name'))

        info = (yield self._client.show(mci.self)).soul

        if self._dry:
            self.log.info('Would delete MCI %s' % info['name'])
            raise gen.Return()

        self.log.info('Deleting MCI %s' % info['name'])
        yield self._client.destroy_resource(mci)
