# TO-BE-NAMED: Deployment Automator

Automated Deployment Engine

## Basic Use

TODO

### Credentials

TODO

### DSL

TODO

## Development

### Class/Object Architecture

    kingpin.rb
    |
    +-- deployment.Deployer
        | Executes a deployment based on the supplied DSL.
        |
        +-- actors.rightsacle
        |   | RightScale Cloud Management Actor
        |
        +-- actors.aws
        |   | Amazon Web Services Actor
        |
        +-- actors.email
        |   | Email Actor
        |
        +-- actors.hipchat
        |   | Hipchat Actor
        |
        +-- actors.librator
            | Librator Metric Actor


### Setup

    # Create a dedicated Python virtual environment and source it
    virtualenv --no-site-packages .venv
    unset PYTHONPATH
    source .venv/bin/activate

    # Install the dependencies
    make build

    # Run the tests
    make test

