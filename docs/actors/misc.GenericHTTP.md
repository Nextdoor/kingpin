##### misc.GenericHTTP

Does a GET or a POST to a specified URL.

**Options**

  * `url`
  * `data` - Optional POST data as a `dict`ionary.
  * `username` - optional for HTTPAuth.
  * `password` - optional for HTTPAuth.

Examples

    { "url": "http://example.com/rest/api/v1?id=123&action=doit",
      "username": "secret"
      "password": "%SECRET_PASSWORD%"
    }

**Dry Mode**

Will not do anything in dry mode except print a log statement.
