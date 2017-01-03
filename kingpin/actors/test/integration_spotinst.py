"""Tests for the actors.spotinst package"""

from nose.plugins.attrib import attr
import uuid
import os

from tornado import testing

from kingpin.actors import spotinst

UUID = uuid.uuid4().hex


__author__ = 'Matt Wise <matt@nextdoor.com>'


class IntegrationSpotinstElastiGroup(testing.AsyncTestCase):

    """Integration tests against the Spotinst API.

    These tests actually hit the Spotinst API and test that the code
    works, as well as validate that the API credentials are working properly.

    Require environment variables:
      SPOTINST_TOKEN
      SECGRP
      SUBNET
      ZONE
      AMI
    """

    integration = True
    region = 'us-east-1'
    group_name = 'kingpin-%s' % UUID
    config = 'examples/test/spotinst.elastigroup/unittest.json'

    @attr('spotinst', 'integration', 'dry')
    @testing.gen_test(timeout=60)
    def integration_01a_create_elastigroup_dry(self):
        actor = spotinst.ElastiGroup(
            dry=True,
            init_tokens=os.environ,
            options={
                'name': self.group_name,
                'state': 'present',
                'config': self.config,
            })
        res = yield actor.execute()
        self.assertEquals(res, None)

    @attr('spotinst', 'integration', 'dry')
    @testing.gen_test(timeout=60)
    def integration_01b_create_elastigroup(self):
        actor = spotinst.ElastiGroup(
            dry=False,
            init_tokens=os.environ,
            options={
                'name': self.group_name,
                'state': 'present',
                'config': self.config,
            })
        res = yield actor.execute()
        self.assertEquals(res, None)

    @attr('spotinst', 'integration', 'dry')
    @testing.gen_test(timeout=60)
    def integration_09a_delete_elastigroup(self):
        actor = spotinst.ElastiGroup(
            dry=False,
            init_tokens=os.environ,
            options={
                'name': self.group_name,
                'state': 'absent',
                'config': self.config,
            })
        res = yield actor.execute()
        self.assertEquals(res, None)
