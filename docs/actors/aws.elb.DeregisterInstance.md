##### kingpin.actors.aws.elb.DeregisterInstance

Remove EC2 instance(s) from an ELB.
    
    http://boto.readthedocs.org/en/latest/ref/elb.html
    #boto.ec2.elb.loadbalancer.LoadBalancer.deregister_instances
    

**Options**

* `elb` - str: Name of the ELB
* `instances` - str, list: Instance id, or list of ids
* `region` - str: AWS region (or zone) name, like us-west-2

**Example**

    {
        "actor": "aws.elb.DeregisterInstance",
        "desc": "Run DeregisterInstance",
        "options": {
            "elb": "fill-in",
            "instances": "fill-in",
            "region": "fill-in"
        }
    }

**Dry run**

Will find the ELB but not take any actions regarding the instances.
