##### kingpin.actors.pingdom.Pause

Start Pingdom Maintenance.
    
    Pause a particular "check" on Pingdom.

**Options**

* `name` - str: Name of the check

**Example**

    {
        "actor": "pingdom.Pause",
        "desc": "Run Pause",
        "options": {
            "name": "fill-in"
        }
    }

**Dry run**

Will assert that the check name exists, but not take any action on it.
