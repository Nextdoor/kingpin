Kingpin: Deployment Automation Engine
=====================================

|doc_status|_ |pypi_download|_

*Kingpin: the chief element of any system, plan, or the like.*

Kingpin provides 3 main functions:

-  **API Abstraction** - Job instructions are provided to Kingpin via a JSON based DSL (read below). The schema is strict and consistent from one action to another.
-  **Automation Engine** - Kingpin leverages python's `tornado <http://tornado.readthedocs.org>`_ engine.
-  **Parallel Execution** - Aside from non-blocking network IO, Kingpin can execute any action in parallel with another. (Read group.Async below)

Documentation
-------------

Documentation is hosted at `https://kingpin.readthedocs.io <https://kingpin.readthedocs.io>`_

.. |doc_status| image:: https://readthedocs.org/projects/kingpin/badge/?version=latest
.. _doc_status: https://kingpin.readthedocs.org
.. |pypi_download| image:: https://badge.fury.io/py/kingpin.png
.. _pypi_download: https://pypi.python.org/pypi/kingpin
