Create an Amazon S3 Bucket
==========================

This tutorial describes how to create an Amazon Simple Storage Service (S3) bucket
using either the AWS Management Console or the AWS Command Line Interface (CLI).

S3 buckets are commonly used for:
- Long-term storage of model input and output data
- Sharing data across AWS services (e.g., EC2, FSx, ParallelCluster)
- Backups and archival

This guide assumes you already have access to an AWS account and sufficient IAM permissions.


Prerequisites
-------------

Before creating an S3 bucket, ensure that:

- You have access to the AWS Management Console or AWS CLI
- Your IAM role or user has permission to create S3 buckets
- You know which AWS region you want to use (typically the same region as your EC2/FSx resources)


Method 1: Create an S3 Bucket via AWS Management Console
----------------------------------------------------------

This method is recommended for first-time users or one-off bucket creation.

Step 1: Open the S3 Console
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Sign in to the AWS Management Console.
2. In the searching bar, searching for **S3**
3. Click **Create bucket**.


Step 2: Configure Bucket Settings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Bucket name**
  
  - Must be globally unique across all AWS accounts
  - Use lowercase letters, numbers, and hyphens only
  - Example: ``imi-gchp-test``

- All others can be left as default

Step 3: Create the Bucket
~~~~~~~~~~~~~~~~~~~~~~~~~

Click **Create bucket**.  
The bucket will be available immediately after creation.

Method 2: Create an S3 Bucket via AWS CLI
--------------------------------------------

This method is recommended for automation, scripting, and reproducible workflows.

Step 1: Configure AWS CLI
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Ensure the AWS CLI is :ref:`installed <aws-cli-install>` and :ref:`configured <aws-configure>`

Step 2: Create the Bucket
~~~~~~~~~~~~~~~~~~~~~~~~~

- **For the us-east-1 region**:

  .. code-block:: bash

    aws s3api create-bucket \
        --bucket imi-gchp-test \
        --region us-east-1

- **For any other region**:
  
  .. code-block:: bash

    aws s3api create-bucket \
        --bucket acmg-gchp-output \
        --region us-west-2 \
        --create-bucket-configuration LocationConstraint=us-west-2

.. note::

    To set up :ref:`DRA <dra>`, we need to have S3 and FSx in the **same region**


Verification
------------

List all S3 buckets::

  aws s3 ls

Confirm the bucket exists and is in the expected region.


Notes and Best Practices
------------------------

- S3 bucket names are global and cannot be reused once deleted (for some time).
- Keep buckets private by default.
- Always create buckets in the same region as compute and storage resources.
- For large-scale data movement between S3 and FSx, consider using FSx Data Repository Associations.


Next Steps
----------

After creating a bucket, you may want to:

    - Upload data to the bucket
    - Attach bucket access permissions to IAM roles
    - Associate the bucket with an FSx for Lustre file system
