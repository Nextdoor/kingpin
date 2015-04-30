##### kingpin.actors.aws.iam.DeleteCert

Delete an existing SSL Cert in AWS IAM.

    http://boto.readthedocs.org/en/latest/ref/iam.html
    #boto.iam.connection.IAMConnection.delete_server_cert
    

**Options**

* `name` - str: The name for the server certificate.

**Example**

    {
        "actor": "aws.iam.DeleteCert",
        "desc": "Run DeleteCert",
        "options": {
            "name": "fill-in"
        }
    }

**Dry run**

Will find the cert by name or raise an exception if it's not found.
