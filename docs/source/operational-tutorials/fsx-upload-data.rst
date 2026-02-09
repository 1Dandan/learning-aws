Data transfer between FSx and S3 bucket
==========================================

This section describes two approaches for transferring data between an
Amazon FSx for Lustre file system and an Amazon S3 bucket.

Launch an EC2 instance for data transfer
-----------------------------------------

In this approach, data transfer is performed through a dedicated EC2 instance.
This instance is used **only for data movement**, not for computation.

- Launch EC2 instance

   - Launch a **single EC2 instance** (not a ParallelCluster)
   - The instance must be in the **same VPC** as the FSx file system
   - Mount the FSx file system on the instance

- Data transfer commands

   - Transfer data from S3 to FSx: ``aws s3 sync s3://<bucket>/input /fsx/input``

   - Transfer data from FSx to S3: ``aws s3 sync /fsx/output s3://<bucket>/output``

- Terminate instance

   - After data transfer is complete, terminate the EC2 instance to avoid unnecessary charges.
   - Instance type recommendation: 
     A compute-optimized instance type is recommended for data transfer tasks (e.g. ``c6i.large``).

- Python tools for data transfer: Python package such as ``boto3`` for data downloading from S3 bucket. 
  
  - Refer to the `detailed tutorial <https://geos-chem.readthedocs.io/en/stable/geos-chem-shared-docs/doc/gcid-awscli-tutorial.html>`_ 
    for downloading GEOS-Chem input data on AWS.
  - `Example scripts <https://github.com/geoschem/integrated_methane_inversion/blob/main/src/utilities/download_aws_file.py>`_ 
    for downloading data on AWS.

.. _dra:

Data repository association (DRA)
-----------------------------------------

FSx for Lustre **Data Repository Associations (DRA)** provide significantly
higher performance than ``aws s3 sync`` for transferring data between FSx
and S3.

With DRA, data transfer is handled natively by the AWS service rather than
through an EC2 instance.

Requirements
^^^^^^^^^^^^

- The FSx file system and the S3 bucket reside in the **same AWS account** (account ID, not IAM user)
- The FSx file system and the S3 bucket are in the **same region**
- The S3 bucket to be linked allows FSx access specified in the :ref:`permissions <fsx_s3_perm>`.
- If these requirements are not met, DRA cannot be used or data cannot be loaded.

Create DRA association
^^^^^^^^^^^^^^^^^^^^^^^

Through console
~~~~~~~~~~~~~~~~~
     
Specify through **Data repository import/export (DRA)** tab when creating a FSx file system

Assume an FSx for Lustre file system is mounted on an EC2 instance at::

  /fsx_input

Two data repository associations (DRAs) are created with the following settings:

- **DRA 1**

  - File system path: ``/ExtData``
  - S3 path: ``s3://dzhang-imi-gchp-test/ExtData``

- **DRA 2**

  - File system path: ``/blended-tropomi``
  - S3 path: ``s3://dzhang-imi-gchp-test/blended-tropomi``

.. note::

  - **Select all import policies and deselect all export policies** 
    so that S3 → FSx synchronization is enabled while FSx → S3 synchronization is disabled.
  - On AWS console, we cannot create multiple DRAs at once. 
    We can modify DRA settings after FSx is created by:
    - Go to AWS Console → FSx
    - Select your FSx for Lustre file system
    - Open the **Data repository** tab
    - Click **Create data repository association**

In this case, the linked S3 data will appear locally on the EC2 instance as::

  /fsx_input/ExtData/
  /fsx_input/blended-tropomi/

The local mount point (``/fsx_input``) corresponds to the root of the FSx file system.
Each data repository association creates a directory directly under this root,
with contents mirrored from the associated S3 prefix.


Through CLI
~~~~~~~~~~~~~

Data repository associations (DRA) can be added during creation or afterwards
using ``aws fsx create-data-repository-association``.

You must provide an IAM Role ARN that FSx can assume to 
access S3 (trusted by fsx.amazonaws.com and allowed S3 actions).

.. code-block:: bash

  # Create two Data Repository Associations (DRAs).
  # Note: DRA file system paths cannot overlap (e.g., /ExtData and /ExtData/subdir).
  # DRAs are supported on FSx for Lustre 2.12/2.15 file systems (excluding scratch_1).

  # DRA 1: Import-only (recommended for static input data like ExtData)
  aws fsx create-data-repository-association \
    --file-system-id "$FSX_ID" \
    --file-system-path "/ExtData" \
    --data-repository-path "s3://dzhang-imi-gchp-test/ExtData" \
    --batch-import-meta-data-on-create \
    --s3 '{
      "AutoImportPolicy": {"Events": ["NEW","CHANGED","DELETED"]}
    }' \
    --tags Key=Name,Value=dra-extdata \
    --client-request-token dra-extdata-001

  # DRA 2: Import-only (or add AutoExportPolicy if you truly want FSx -> S3 sync)
  aws fsx create-data-repository-association \
    --file-system-id "$FSX_ID" \
    --file-system-path "/blended-tropomi" \
    --data-repository-path "s3://dzhang-imi-gchp-test/blended-tropomi" \
    --batch-import-meta-data-on-create \
    --s3 '{
      "AutoImportPolicy": {"Events": ["NEW","CHANGED","DELETED"]}
    }' \
    --tags Key=Name,Value=dra-blended-tropomi \
    --client-request-token dra-tropomi-001


Verify DRA exists

.. code-block:: bash

  aws fsx describe-data-repository-associations \
    --filters Name=file-system-id,Values="$FSX_ID" \
    --query "Associations[*].{Path:FileSystemPath,S3:DataRepositoryPath,State:Lifecycle}"

.. important::

    FSx for Lustre accesses S3 through :ref:`an IAM service role <fsx_s3_perm>` trusted by
    ``fsx.amazonaws.com``. When enabling DRA, ensure that the associated
    IAM role has permission to ``s3:GetObject``, ``s3:PutObject``, and
    ``s3:ListBucket`` on the **linked S3 bucket or prefix**.

.. note::

   - DRA is particularly useful for large datasets
   - EC2-based ``aws s3 sync`` remains a flexible fallback option
