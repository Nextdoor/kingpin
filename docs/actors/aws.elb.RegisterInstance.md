##### kingpin.actors.aws.elb.RegisterInstance

Add an EC2 instance to a load balancer.

    http://boto.readthedocs.org/en/latest/ref/elb.html
    #boto.ec2.elb.ELBConnection.register_instances
    

**Options**

* `elb` - str: Name of the ELB
* `instances` - str, list: Instance id, or list of ids. Default "self" id.
* `region` - str: AWS region (or zone) name, like us-west-2
* `enable_zones` - bool: add all available AZ to the elb. Default: True

**Example**

    {
        "actor": "aws.elb.RegisterInstance",
        "desc": "Run RegisterInstance",
        "options": {
            "elb": "prod-loadbalancer",
            "instances": "i-123456",
            "region": "us-east-1",
        }
    }

**Dry run**

Will find the specified ELB, but not take any actions regarding instances.
