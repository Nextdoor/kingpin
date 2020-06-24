"""Tests for the actors.packagecloud package"""

import datetime
import mock

from tornado import testing

from kingpin.actors import exceptions
from kingpin.actors import packagecloud
from kingpin.actors.test.helper import mock_tornado, tornado_value

__author__ = 'Charles McLaughlin <charles@nextdoor.com>'

ALL_PACKAGES_MOCK_RESPONSE = [
    {'name': 'unittest', 'uploader_name': 'unittest',
     'created_at': '2015-07-07T20:27:18.000Z',
     'distro_version': 'ubuntu/trusty',
     'filename': 'unittest_0.2-1_all.deb', 'epoch': 0,
     'version': '0.2', 'private': True, 'release': '1',
     'package_url': ('/api/v1/repos/unittest/test/package/deb/ubuntu/'
                     'trusty/unittest/all/0.2-1.json'),
     'type': 'deb',
     'package_html_url': ('/unittest/test/packages/ubuntu/trusty/'
                          'unittest_0.2-1_all.deb'),
     'repository_html_url': '/unittest/test'},

    {'name': 'unittest', 'uploader_name': 'unittest',
     'created_at': '2014-07-07T20:27:18.000Z',
     'distro_version': 'ubuntu/trusty',
     'filename': 'unittest_0.1-1_all.deb', 'epoch': 0,
     'version': '0.1', 'private': True, 'release': '1',
     'package_url': ('/api/v1/repos/unittest/test/package/deb/ubuntu/'
                     'trusty/unittest/all/0.1-1.json'),
     'type': 'deb',
     'package_html_url': ('/unittest/test/packages/ubuntu/trusty/'
                          'unittest_0.1-1_all.deb'),
     'repository_html_url': '/unittest/test'}
]


def _get_older_than():
    """ Method for getting an `older_than` value which is used in a few
    tests below.

    The tests specifically look for the second package in
    ALL_PACKAGES_MOCK_RESPONSE, as it's older than the first"""

    created_at = datetime.datetime.strptime(
        ALL_PACKAGES_MOCK_RESPONSE[0]['created_at'],
        '%Y-%m-%dT%H:%M:%S.%fZ')
    older_than = datetime.datetime.now() - created_at + datetime.timedelta(
        seconds=600)  # Adding 5m in case the tests run long
    return older_than


class TestPackagecloudBase(testing.AsyncTestCase):

    """Unit tests for the packagecloud Base actor."""

    def setUp(self, *args, **kwargs):
        super(TestPackagecloudBase, self).setUp(*args, **kwargs)
        packagecloud.TOKEN = 'Unittest'
        packagecloud.ACCOUNT = 'Unittest'
        self.maxDiff = None

    @testing.gen_test
    def test_init_missing_token(self):
        # Un-set the token and make sure the init fails
        packagecloud.TOKEN = None
        with self.assertRaises(exceptions.InvalidCredentials):
            packagecloud.PackagecloudBase('Unit Test Action', {})

    @testing.gen_test
    def test_init_missing_account(self):
        # Un-set the account and make sure the init fails
        packagecloud.ACCOUNT = None
        with self.assertRaises(exceptions.InvalidCredentials):
            packagecloud.PackagecloudBase('Unit Test Action', {})

    @testing.gen_test
    def test_get_all_packages(self):
        actor = packagecloud.PackagecloudBase('Unit test action', {})
        actor._packagecloud_client = mock.Mock()
        actor._packagecloud_client.packages().http_get = mock_tornado(
            ALL_PACKAGES_MOCK_RESPONSE)
        all_packages = yield actor._get_all_packages(repo='unittest')
        self.assertEqual(all_packages, ALL_PACKAGES_MOCK_RESPONSE)

    @testing.gen_test
    def test_get_package_versions(self):
        actor = packagecloud.PackagecloudBase('Unit test action', {})
        actor._packagecloud_client = mock.Mock()
        actor._packagecloud_client.packages().http_get = mock_tornado(
            ALL_PACKAGES_MOCK_RESPONSE)
        packages = yield actor._get_all_packages(repo='unittest')
        versions = actor._get_package_versions(
            name='unittest', packages=packages)

        self.assertEqual(
            versions,
            [{'created_at': datetime.datetime(2014, 7, 7, 20, 27, 18),
              'name': 'unittest',
              'distro_version': 'ubuntu/trusty',
              'filename': 'unittest_0.1-1_all.deb'},
             {'created_at': datetime.datetime(2015, 7, 7, 20, 27, 18),
              'name': 'unittest',
              'distro_version': 'ubuntu/trusty',
              'filename': 'unittest_0.2-1_all.deb'}])

    @testing.gen_test
    def test_filter_packages(self):
        actor = packagecloud.PackagecloudBase('Unit test action', {})
        actor._packagecloud_client = mock.Mock()
        actor._packagecloud_client.packages().http_get = mock_tornado(
            ALL_PACKAGES_MOCK_RESPONSE)
        packages = yield actor._get_all_packages(repo='unittest')
        packages_list_to_delete = actor._filter_packages(
            regex='unittest', packages=packages)
        self.assertEqual(packages_list_to_delete, set(['unittest']))

    @testing.gen_test
    def test_delete(self):
        actor = packagecloud.PackagecloudBase('Unit test action', {})
        actor._packagecloud_client = mock.Mock()
        actor._packagecloud_client.packages().http_get = mock_tornado(
            ALL_PACKAGES_MOCK_RESPONSE)
        actor._packagecloud_client.delete().http_delete = mock_tornado({})

        deleted_packages = yield actor._delete(
            regex='unittest', repo='unittest')

        self.assertEqual(deleted_packages,
                         [{'created_at': datetime.datetime(
                             2014, 7, 7, 20, 27, 18),
                             'name': 'unittest',
                             'distro_version': 'ubuntu/trusty',
                             'filename': 'unittest_0.1-1_all.deb'},
                             {'created_at': datetime.datetime(
                                 2015, 7, 7, 20, 27, 18),
                                 'name': 'unittest',
                                 'distro_version': 'ubuntu/trusty',
                                 'filename': 'unittest_0.2-1_all.deb'}])

    @testing.gen_test
    def test_delete_dry(self):
        actor = packagecloud.PackagecloudBase('Unit test action', {})
        actor._packagecloud_client = mock.Mock()
        actor._packagecloud_client.packages().http_get = mock_tornado(
            ALL_PACKAGES_MOCK_RESPONSE)
        actor._packagecloud_client.delete().http_delete = mock_tornado({})
        actor._dry = True

        deleted_packages = yield actor._delete(
            regex='unittest', repo='unittest')

        self.assertEqual(deleted_packages,
                         [{'created_at': datetime.datetime(
                             2014, 7, 7, 20, 27, 18),
                             'name': 'unittest',
                             'distro_version': 'ubuntu/trusty',
                             'filename': 'unittest_0.1-1_all.deb'},
                             {'created_at': datetime.datetime(
                                 2015, 7, 7, 20, 27, 18),
                                 'name': 'unittest',
                                 'distro_version': 'ubuntu/trusty',
                                 'filename': 'unittest_0.2-1_all.deb'}])

    @testing.gen_test
    def test_delete_keep_one(self):
        actor = packagecloud.PackagecloudBase('Unit test action', {})
        actor._packagecloud_client = mock.Mock()
        actor._packagecloud_client.packages().http_get = mock_tornado(
            ALL_PACKAGES_MOCK_RESPONSE)
        actor._packagecloud_client.delete().http_delete = mock_tornado({})

        deleted_packages = yield actor._delete(
            regex='unittest', repo='unittest', number_to_keep=1)

        self.assertEqual(
            deleted_packages,
            [{'created_at': datetime.datetime(2014, 7, 7, 20, 27, 18),
              'name': 'unittest', 'distro_version': 'ubuntu/trusty',
              'filename': 'unittest_0.1-1_all.deb'}])

    @testing.gen_test
    def test_delete_older_than(self):
        actor = packagecloud.PackagecloudBase('Unit test action', {})
        actor._packagecloud_client = mock.Mock()
        actor._packagecloud_client.packages().http_get = mock_tornado(
            ALL_PACKAGES_MOCK_RESPONSE)
        actor._packagecloud_client.delete().http_delete = mock_tornado({})

        older_than = _get_older_than()

        deleted_packages = yield actor._delete(
            regex='unittest', repo='unittest',
            older_than=older_than.total_seconds())

        self.assertEqual(
            deleted_packages,
            [{'created_at': datetime.datetime(2014, 7, 7, 20, 27, 18),
              'name': 'unittest', 'distro_version': 'ubuntu/trusty',
              'filename': 'unittest_0.1-1_all.deb'}])


class TestDelete(testing.AsyncTestCase):

    """Unit tests for the packagecloud Delete actor."""

    def setUp(self, *args, **kwargs):
        super(TestDelete, self).setUp(*args, **kwargs)
        packagecloud.TOKEN = 'Unittest'
        packagecloud.ACCOUNT = 'Unittest'
        self.maxDiff = None

    @testing.gen_test
    def test_bad_regex_packages_to_delete(self):
        with self.assertRaises(exceptions.InvalidOptions):
            packagecloud.Delete(
                'Unit test action',
                {'packages_to_delete': '[', 'repo': 'unittest'})

    @testing.gen_test
    def test_execute(self):
        actor = packagecloud.Delete(
            'Unit test action',
            {'packages_to_delete': 'unittest', 'repo': 'unittest'})
        actor._packagecloud_client = mock.Mock()
        actor._packagecloud_client.packages().http_get = mock_tornado(
            ALL_PACKAGES_MOCK_RESPONSE)
        actor._packagecloud_client.delete().http_delete = mock_tornado({})

        deleted_packages = yield actor._execute()

        self.assertEqual(deleted_packages, None)


class TestDeleteByDate(testing.AsyncTestCase):

    """Unit tests for the packagecloud DeleteByDate actor."""

    def setUp(self, *args, **kwargs):
        super(TestDeleteByDate, self).setUp(*args, **kwargs)
        packagecloud.TOKEN = 'Unittest'
        packagecloud.ACCOUNT = 'Unittest'
        self.maxDiff = None

    @testing.gen_test
    def test_execute(self):
        older_than = _get_older_than()
        actor = packagecloud.DeleteByDate(
            'Unit test action',
            {'packages_to_delete': 'unittest',
             'repo': 'unittest',
             'older_than': int(older_than.total_seconds())})

        actor._packagecloud_client = mock.Mock()
        actor._packagecloud_client.packages().http_get = mock_tornado(
            ALL_PACKAGES_MOCK_RESPONSE)
        actor._packagecloud_client.delete().http_delete = mock_tornado({})

        deleted_packages = yield actor._execute()

        self.assertEqual(deleted_packages, None)


class TestWaitForPackage(testing.AsyncTestCase):

    """Unit tests for the packagecloud WaitForPackage actor."""

    def setUp(self, *args, **kwargs):
        super(TestWaitForPackage, self).setUp(*args, **kwargs)
        packagecloud.TOKEN = 'Unittest'
        packagecloud.ACCOUNT = 'Unittest'
        self.maxDiff = None

    @testing.gen_test
    def test_bad_regex_name(self):
        with self.assertRaises(exceptions.InvalidOptions):
            packagecloud.WaitForPackage(
                'Unit test action',
                {'name': '[', 'version': '1', 'repo': 'unittest'})

    @testing.gen_test
    def test_bad_regex_version(self):
        with self.assertRaises(exceptions.InvalidOptions):
            packagecloud.WaitForPackage(
                'Unit test action',
                {'name': 'unittest', 'version': '[', 'repo': 'unittest'})

    @testing.gen_test
    def test_execute(self):
        actor = packagecloud.WaitForPackage(
            'Unit test action',
            {'name': 'unittest', 'repo': 'unittest', 'version': '0.2'})

        actor._packagecloud_client = mock.Mock()
        actor._packagecloud_client.packages().http_get = mock_tornado(
            ALL_PACKAGES_MOCK_RESPONSE)
        actor._packagecloud_client.delete().http_delete = mock_tornado({})

        matched_packages = yield actor._execute()

        self.assertEqual(matched_packages, None)

    @testing.gen_test
    def test_execute_with_sleep(self):
        actor = packagecloud.WaitForPackage(
            'Unit test action',
            {'name': 'not_found', 'repo': 'unittest', 'version': '0.2',
             'sleep': 1})

        actor._packagecloud_client = mock.Mock()
        actor._packagecloud_client.packages().http_get = mock_tornado(
            ALL_PACKAGES_MOCK_RESPONSE)
        actor._search = mock.Mock(
            side_effect=[tornado_value([]), tornado_value(['something'])])
        yield actor._execute()
        self.assertEqual(actor._search.call_count, 2)

    @testing.gen_test
    def test_search(self):
        actor = packagecloud.WaitForPackage('Unit test action', {
            'name': 'unittest', 'repo': 'unittest', 'version': '0.2'})
        actor._packagecloud_client = mock.Mock()
        actor._packagecloud_client.packages().http_get = mock_tornado(
            ALL_PACKAGES_MOCK_RESPONSE)

        matched_packages = yield actor._search(
            repo='unittest', name='unittest', version='0.2')

        self.assertEqual(matched_packages, [ALL_PACKAGES_MOCK_RESPONSE[0]])
