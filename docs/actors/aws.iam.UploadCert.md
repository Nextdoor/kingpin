##### kingpin.actors.aws.iam.UploadCert

Uploads a new SSL Cert to AWS IAM.

    http://boto.readthedocs.org/en/latest/ref/iam.html
    #boto.iam.connection.IAMConnection.upload_server_cert
    
**Options**

* `private_key_path` - str: Path to the private key.
* `path` - str: The AWS "path" for the server certificate. Default: "/"
* `public_key_path` - str: Path to the public key certificate.
* `name` - str: The name for the server certificate.
* `cert_chain_path` - str: Path to the certificate chain. Optional.

**Example**

    {
        "actor": "aws.iam.UploadCert",
        "desc": "Upload a new cert",
        "options": {
            "name": "new-cert",
            "private_key_path": "/cert.key",
            "public_key_path": "/cert.pem",
            "cert_chain_path": "/cert-chain.pem"
        }
    }

**Dry run**

Checks that the passed file paths are valid. In the future will also validate
that the files are of correct format and content.
