##### kingpin.actors.pingdom.Unpause

Stop Pingdom Maintenance.
    
    Unpause a particular "check" on Pingdom.

**Options**

* `name` - str: Name of the check

**Example**

    {
        "actor": "pingdom.Unpause",
        "desc": "Run Unpause",
        "options": {
            "name": "fill-in"
        }
    }

**Dry run**

Will assert that the check name exists, but not take any action on it.
