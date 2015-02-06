##### kingpin.actors.aws.elb.AddInstance

Add an EC2 instance to a load balancer.

    http://boto.readthedocs.org/en/latest/ref/elb.html
    #boto.ec2.elb.ELBConnection.register_instances
    

**Options**

* `elb` - str: Name of the ELB
* `instance_id` - str, list: Instance id, or list of ids
* `region` - str: AWS region name, like us-west-2

**Example**

    {
        "actor": "aws.elb.AddInstance",
        "desc": "Run AddInstance",
        "options": {
            "elb": "fill-in",
            "instance_id": "fill-in",
            "region": "fill-in"
        }
    }

**Dry run**

Will find the specified ELB, but not take any actions regarding instances.
