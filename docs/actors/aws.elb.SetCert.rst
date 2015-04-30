##### kingpin.actors.aws.elb.SetCert

Find a server cert in IAM and use it for a specified ELB.

**Options**

* `region` - str: AWS region (or zone) name, like us-west-2
* `name` - str: Name of the ELB
* `cert_name` - str: Unique IAM certificate name, or ARN
* `port` - int: Port associated with the cert Default: 443

**Example**

    {
        "actor": "aws.elb.SetCert",
        "desc": "Run SetCert",
        "options": {
            "cert_name": "new-cert",
            "name": "some-elb",
            "region": "us-west-2"
        }
    }

**Dry run**

Will check that ELB and Cert names are existent, and will also check that the 
credentials provided for AWS have access to the new cert for ssl.
