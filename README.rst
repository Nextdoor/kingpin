Kingpin: Deployment Automation Engine
=====================================

.. image:: https://travis-ci.org/Nextdoor/kingpin.svg?branch=master
.. image:: https://readthedocs.org/projects/kingpin/badge/?version=latest
.. image:: https://pypip.in/d/kingpin/badge.png
.. image:: https://badge.fury.io/py/kingpin.png

*Kingpin: the chief element of any system, plan, or the like.*

Kingpin provides 3 main functions:

-  **API Abstraction** - Job instructions are provided to Kingpin via a JSON based DSL (read below). The schema is strict and consistent from one action to another. 
-  **Automation Engine** - Kingpin is leverages python's `tornado <http://tornado.readthedocs.org>`_ engine.
-  **Parallel Execution** - Aside from non-blocking network IO, Kingpin can execute any action in parallel with another. (Read group.Async below)

Documentation
-------------

Documentation is hosted at `https://kingpin.readthedocs.org <https://kingpin.readthedocs.org>`_