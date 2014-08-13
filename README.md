# Kingpin: The Deployment Director

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
        +-- actors.rightscale
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

### Postfix on Mac OSX

If you want to develop on a Mac OSX host, you need to enable email the
*postfix* daemon on your computer. Here's how!

Modify */Syatem/Library/LaunchDaemons/org.postfix.master.plist*:

    --- /System/Library/LaunchDaemons/org.postfix.master.plist.bak	2014-06-02 11:45:24.000000000 -0700
    +++ /System/Library/LaunchDaemons/org.postfix.master.plist	2014-06-02 11:47:07.000000000 -0700
    @@ -9,8 +9,6 @@
            <key>ProgramArguments</key>
            <array>
                   <string>master</string>
    -              <string>-e</string>
    -              <string>60</string>
            </array>
            <key>QueueDirectories</key>
            <array>
    @@ -18,5 +16,8 @@
            </array>
            <key>AbandonProcessGroup</key>
            <true/>
    +
    +        <key>KeepAlive</key>
    +       <true/>
     </dict>
     </plist>

Restart the service:

    cd /System/Library/LaunchDaemons
    sudo launchctl unload org.postfix.master.plist 
    sudo launchctl load org.postfix.master.plist
