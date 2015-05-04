Security
--------

URLLIB3 Warnings Disabled
^^^^^^^^^^^^^^^^^^^^^^^^^

Recently urllib3 library has started issuing
`InsecurePlatformWarning <https://urllib3.readthedocs.org/en/latest/security.html#insecureplatformwarning>`__.
We suppress urllib3 warnings to limit log output to Kingping's own.
