Security
--------

Recently urllib3 library has started issuing
`InsecurePlatformWarning <https://urllib3.readthedocs.org/en/latest/security.html#insecureplatformwarning>`__.
We `suppress <kingpin/actors/rightscale/api.py>`__ urllib3 warnings to
limit log output to Kingping's own.
