Installation
------------

The simplest installation method is via
`PyPI <https://pypi.python.org/pypi/kingpin>`__.

.. code-block:: bash

    $ pip install kingpin

Note, we *strongly* recommend running the code inside a Python virtual
environment. All of our examples below will show how to do this.

Github Checkout/Install
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    $ virtualenv .venv --no-site-packages
    New python executable in .venv/bin/python
    Installing setuptools, pip...done.
    $ source .venv/bin/activate
    (.venv) $ git clone https://github.com/Nextdoor/kingpin
    Cloning into 'kingpin'...
    remote: Counting objects: 1824, done.
    remote: Compressing objects: 100% (10/10), done.
    remote: Total 1824 (delta 4), reused 0 (delta 0)
    Receiving objects: 100% (1824/1824), 283.35 KiB, done.
    Resolving deltas: 100% (1330/1330), done.
    (.venv)$ cd kingpin/
    (.venv)$ pip install .
    zip_safe flag not set; analyzing archive contents...
    ...

Direct PIP Install
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

    $ virtualenv .venv --no-site-packages
    New python executable in .venv/bin/python
    Installing setuptools, pip...done.
    $ source .venv/bin/activate
    (.venv) $ git clone https://github.com/Nextdoor/kingpin
    (.venv)$ pip install git+https://github.com/Nextdoor/kingpin.git
    Downloading/unpacking git+https://github.com/Nextdoor/kingpin.git
      Cloning https://github.com/Nextdoor/kingpin.git (to master) to /var/folders/j6/qyd2dp6n3f156h6xknndt35m00010b/T/pip-H9LwNt-build
    ...

Zip File Packaging
~~~~~~~~~~~~~~~~~~

For the purpose of highly reliable and fast installations, you can also execute
``make package`` to generate a Python-executable ``.zip`` file. This file is built
with all of the dependencies installed inside of it, and can be executed on the
command line very simply:

.. code-block:: bash

    $ virtualenv .venv --no-site-packages
    New python executable in .venv/bin/python
    Installing setuptools, pip...done.
    $ source .venv/bin/activate
    $ make kingpin.zip
    $ python kingpin.zip --version
    0.2.5

**VirtualEnv Note**

Its not strictly necessary to set up the virtual environment like we did in the
example above -- but it helps prevent any confusion during the build
process around what packages are available or are not.
