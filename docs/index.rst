Kingpin: Deployment Automation Engine
=====================================


*Kingpin: the chief element of any system, plan, or the like.*

Kingpin provides 3 main functions:

-  **API Abstraction** - Job instructions are provided to Kingpin via a
   JSON based DSL (read below). The schema is strict and consistent from
   one action to another.
-  **Automation Engine** - Kingpin is leverages python's
   `tornado <http://tornado.readthedocs.org/>`__ engine.
-  **Parallel Execution** - Aside from non-blocking network IO, Kingpin
   can execute any action in parallel with another. (Read group.Async
   below)

.. toctree::
   :maxdepth: 3

   installation
   basicuse
   actors
   security

.. toctree::
   :maxdepth: 3

   development

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

