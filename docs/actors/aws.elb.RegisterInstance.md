##### kingpin.actors.aws.elb.RegisterInstance

Add an EC2 instance to a load balancer.

    http://boto.readthedocs.org/en/latest/ref/elb.html
    #boto.ec2.elb.ELBConnection.register_instances
    

**Options**

* `elb` - str: Name of the ELB
* `instances` - str, list: Instance id, or list of ids
* `region` - str: AWS region name, like us-west-2

**Example**

    {
        "actor": "aws.elb.RegisterInstance",
        "desc": "Run RegisterInstance",
        "options": {
            "elb": "fill-in",
            "instances": "fill-in",
            "region": "fill-in"
        }
    }

**Dry run**

Will find the specified ELB, but not take any actions regarding instances.
