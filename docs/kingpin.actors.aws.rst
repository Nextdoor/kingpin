Amazon Web Services
~~~~~~~~~~~~~~~~~~~

The AWS Actors allow you to interact with the resources (such as SQS and ELB)
inside your Amazon AWS account. These actors all support dry runs properly, but
each actor has its own caveats with ``dry=True``. Please read the instructions
below for using each actor.

**Required Environment Variables**

- ``AWS_ACCESS_KEY_ID`` - Your AWS access key
- ``AWS_SECRET_ACCESS_KEY`` - Your AWS secret

.. automodule:: kingpin.actors.aws.cloudformation
   :members:
   :exclude-members: CloudFormationBaseActor, CloudFormationError, InvalidTemplate, StackAlreadyExists, StackNotFound
.. automodule:: kingpin.actors.aws.elb
   :members:
   :exclude-members: CertNotFound, p2f, ELBBaseActor
.. automodule:: kingpin.actors.aws.iam
   :members:
   :exclude-members: IAMBaseActor
.. automodule:: kingpin.actors.aws.sqs
   :members:
   :exclude-members: QueueNotFound, QueueDeletionFailed
