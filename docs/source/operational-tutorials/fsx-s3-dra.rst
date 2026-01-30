Data transfer between FSx and S3 bucket
=======================================

This section describes two approaches for transferring data between an
Amazon FSx for Lustre file system and an Amazon S3 bucket.

Launch EC2 instance for data transfer
-----------------------------------------

In this approach, data transfer is performed through a dedicated EC2 instance.
This instance is used **only for data movement**, not for computation.

Launch EC2 instance
^^^^^^^^^^^^^^^^^^^

- Launch a **single EC2 instance** (not a ParallelCluster)
- The instance must be in the **same VPC** as the FSx file system
- Mount the FSx file system on the instance

Data transfer commands
^^^^^^^^^^^^^^^^^^^^^^

Transfer data from S3 to FSx:

.. code-block:: bash

   aws s3 sync s3://<bucket>/input /fsx/input

Transfer data from FSx to S3:

.. code-block:: bash

   aws s3 sync /fsx/output s3://<bucket>/output

Terminate instance
^^^^^^^^^^^^^^^^^^

After data transfer is complete, terminate the EC2 instance to avoid
unnecessary charges.

Instance type recommendation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A compute-optimized instance type is recommended for data transfer tasks.

Examples:

- ``c6i.large``
- ``c6i.xlarge``

Python tools for data transfer
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Python package such as `boto3` for data downloading from S3 bucket. Example can be found 
[here](https://github.com/geoschem/integrated_methane_inversion/blob/main/src/utilities/download_aws_file.py)


Data repository association (DRA)
-------------------------------------

FSx for Lustre **Data Repository Associations (DRA)** provide significantly
higher performance than ``aws s3 sync`` for transferring data between FSx
and S3.

With DRA, data transfer is handled natively by the AWS service rather than
through an EC2 instance.

Requirements
^^^^^^^^^^^^

DRA requires that:

- The FSx file system and the S3 bucket reside in the **same AWS account**
  (account ID, not IAM user)
- The FSx file system and the S3 bucket are in the **same region**

If these requirements are not met, DRA cannot be used.

Notes
^^^^^

- DRA is particularly useful for large datasets
- EC2-based ``aws s3 sync`` remains a flexible fallback option
