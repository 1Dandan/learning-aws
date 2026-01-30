AWS APIs
========

IAM permissions define which AWS service APIs are allowed to be called.

All AWS infrastructure provisioning and management operations are ultimately
performed through AWS APIs, regardless of whether the interaction occurs via
the AWS Console, CLI tools, or SDKs.

Checking AWS API permissions
----------------------------

To identify the AWS identity currently in use, run:

.. code-block:: bash

   aws sts get-caller-identity

This command returns the ARN of the IAM user or IAM role associated with the
current credentials.

Simulating API permissions
--------------------------

To check whether a specific AWS API action is allowed, run:

.. code-block:: bash

   aws iam simulate-principal-policy \
     --policy-source-arn <your_IAM_ARN> \
     --action-names <service_API_name1> <service_API_name2> ...

.. note::

   The ``simulate-principal-policy`` API requires explicit IAM permissions
   and may be restricted in organization-managed AWS accounts.

Practical considerations
------------------------

In practice, the most reliable way to verify permissions is often to:

- Run the intended AWS CLI command
- Inspect the error message if the operation fails

This approach reflects the actual permission evaluation context applied by
AWS.
