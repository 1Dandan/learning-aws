Upload Data to an Amazon S3 Bucket
====================================

This tutorial describes common and recommended methods for uploading data to
an existing Amazon S3 bucket.

Typical use cases include:

    - Uploading model input data
    - Storing simulation outputs
    - Backing up data from EC2 or FSx for Lustre
    - Sharing data across AWS services

This guide assumes that the S3 bucket already exists.


Prerequisites
-------------

Before uploading data to S3, ensure that:

    - You have access to an existing S3 bucket
    - Your IAM user or role has permission to write to the bucket
    - AWS CLI is installed and configured if using command-line methods


Upload Input Data Using Python Scripts (Recommended)
-----------------------------------------------------------

- There is **no data transferring fee** if the two S3 buckets are in the **same region** 
  with only tiny S3 bucket request fee.
- There is storage fee associated with a copied S3 bucket, 
  but the cost is much cheaper than FSx for Lustre and compute cost, see :ref:`pricing <pricing>`

- We first transfer data to S3 in the same AWS account and then we can utilize :ref:`DRA <dra>` to 
  facilitate super fast transferring from S3 to FSx (much faster than ``aws s3 sync``)
- All input data is available in S3 bucket(s), we can copy data in-between S3 buckets.
- List of source bucket name for input data

=========================== ========================================= ========================
Input data                                 S3 bucket name                  Downloading scripts
=========================== ========================================= ========================
GEOS-Chem                   geos-chem (us-west-2); gcgrid (us-east-1)  :download:`copy_geoschem_inputdata_s3_to_s3.py <../scripts/copy_geoschem_inputdata_s3_to_s3.py>`
Blended TROPOMI             blended-tropomi-gosat-methane (us-west-2) :download:`copy_blended_TROPOMI_s3_to_s3.py <../scripts/copy_blended_TROPOMI_s3_to_s3.py>`
=========================== ========================================= ========================

Check the bucket region by::

  aws s3api head-bucket --bucket <bucket_name>


.. note::

  - You need to run the helper scripts to download inputs with AWS credential 
    either through IAM user credential or assumed credential from an EC2 instance
  - The region is listed in the bracket adjacent to S3 bucket name. 
    For example, the bucket name is ``gcgrid`` instead of ``gcgrid (us-east-1)``

Downloading scripts tutorials
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- For GEOS-Chem input data

  - Generate dryrun log using GCClassic dryrun option, see the instructions 
    `here <https://geos-chem.readthedocs.io/en/stable/gcclassic-user-guide/dry-run.html>`_
  - Use the helper scripts :download:`copy_geoschem_inputdata_s3_to_s3.py <../scripts/copy_geoschem_inputdata_s3_to_s3.py>`

    .. code-block:: bash

      python copy_geoschem_inputdata_s3_to_s3.py \
        <dryrun_log> \
        --dest-bucket <bucket> \
        [--dest-prefix <prefix>] \
        [--dryrun]
    
    An example dry run::

      python copy_geoschem_inputdata_s3_to_s3.py \
        geoschem.dryrun.log \
        --dest-bucket dzhang-imi-gchp-test \
        --dest-prefix ExtData \
        --dryrun
    
    You will see similar output::

      =============Mirror ExtData referenced by dry-run log=============
      Log:        geoschem.dryrun.log
      Source:     s3://gcgrid/
      Dest:       s3://dzhang-imi-gchp-test/ExtData/
      Mode:       found+missing
      Objects:    77
      Dryrun:     True | Overwrite: False
      ===================================================================
      [DRYRUN] s3://gcgrid/GEOS_0.25x0.3125/GEOS_FP/2011/01/GEOSFP.20110101.CN.025x03125.nc 
      -> s3://dzhang-imi-gchp-test/ExtData/GEOS_0.25x0.3125/GEOS_FP/2011/01/
      GEOSFP.20110101.CN.025x03125.nc
      ...
      ===================================================================
      Done. copied=0 skipped=0 failed=0 dryrun=77
      ===================================================================

    If you are satisfied with the dryrun output, just remove ``--dryrun`` for a real copy

- For satellite data
 
  User the helper scripts :download:`copy_blended_TROPOMI_s3_to_s3.py <../scripts/copy_blended_TROPOMI_s3_to_s3.py>`.
  
  .. code-block:: bash

    python copy_blended_TROPOMI_s3_to_s3.py \
      <start-time> <end-time> \
      <dest-bucket> \
      [--dest-prefix PREFIX] \
      [--src-bucket NAME] \
      [--dryrun]
  
  An example dry run::

    python copy_blended_TROPOMI_s3_to_s3.py \
      20240501 20240502 dzhang-imi-gchp-test \
      --dest-prefix blended-tropomi/ --dryrun
  
  You will see similar message like::

    =============Copying S3 -> S3 (date-filtered)=============
    Range: [20240501, 20240502)
    Source: s3://blended-tropomi-gosat-methane/
    Dest:   s3://dzhang-imi-gchp-test/blended-tropomi/
    Files matched: 15
    [DRYRUN] copy s3://blended-tropomi-gosat-methane/data/2024-05/
    S5P_BLND_L2__CH4____20240501T115126_20240501T133256_33938_03_020600_20240918T125812.nc 
    -> s3://dzhang-imi-gchp-test/blended-tropomi/
    S5P_BLND_L2__CH4____20240501T115126_20240501T133256_33938_03_020600_20240918T125812.nc
    ...
    Done. Success: 15, Failed: 0

  If you are satisfied with the dryrun output, just remove ``--dryrun`` for a real copy


Upload Output Data from FSx for Lustre (Best for Large Outputs)
-------------------------------------------------------------------

When using FSx for Lustre with an S3 Data Repository Association (DRA),
data written to FSx can be automatically synchronized to S3.

Typical workflow::

  /fsx/
  └── output/
      └── Test_Global_1day_c36s10/

With DRA configured:

  - Files written to FSx appear in the associated S3 bucket
  - No explicit ``aws s3 cp`` command is required

This method is recommended for:

  - Large-scale model output
  - ParallelCluster workflows
  - Repeated data transfers

.. note::

  FSx and S3 must be in the same AWS account and region for DRA to work.


Other Official Methods
-------------------------------------------------

Upload Data Using AWS CLI
^^^^^^^^^^^^^^^^^^^^^^^^^^

The AWS CLI is the preferred method for uploading data in most research and
HPC workflows. It is scriptable, restartable, and suitable for large datasets.


Upload a Single File
~~~~~~~~~~~~~~~~~~~~

Use ``aws s3 cp`` to upload an individual file::

  aws s3 cp local_file.nc s3://my-bucket/path/local_file.nc

Example::

  aws s3 cp emis_2020.nc s3://imi-gchp-test/emissions/emis_2020.nc


Upload a Directory Recursively
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To upload an entire directory and preserve its structure::

  aws s3 cp local_directory/ s3://my-bucket/path/ --recursive

Example::

  aws s3 cp ExtData/ s3://acmg-input-data/ExtData/ --recursive

This method is suitable for initial uploads of structured datasets.


Synchronize a Directory (Recommended)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use ``aws s3 sync`` to upload only new or modified files::

  aws s3 sync local_directory/ s3://my-bucket/path/

Example::

  aws s3 sync output/ s3://acmg-gchp-output/Test_Global_1day_c360/

Advantages of ``sync``:

    - Skips unchanged files
    - Safe for repeated execution
    - Ideal for incremental model outputs

Upload Data Using AWS Management Console
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This method is suitable only for small files or one-off uploads.

Steps:
    
    1. Open the S3 service in the AWS Management Console
    2. Select the target bucket
    3. Click **Upload**
    4. Drag and drop files or select them manually
    5. Click **Upload**

Limitations:

    - Not suitable for large datasets
    - No automation
    - Browser-dependent

Common Permission Requirements
------------------------------

Uploading data to S3 typically requires the following IAM permissions::

  s3:PutObject
  s3:PutObjectAcl
  s3:ListBucket

These permissions must apply to:

    - The bucket itself
    - All objects within the bucket

If uploading from EC2 or ParallelCluster:

    - The instance IAM role must have these permissions
    - User permissions on your local machine do not apply


Verification
------------

To verify uploaded objects::

  aws s3 ls s3://my-bucket/path/

To recursively list contents::

  aws s3 ls s3://my-bucket/path/ --recursive


.. note::

  - Although S3 paths resemble Linux directories, S3 is not a filesystem:
    operations such as ``mv`` or ``rename`` rewrite object keys rather than
    modifying directory metadata.
  - Always include the trailing ``/`` when operating on a “folder”.
    The trailing ``/`` tells the AWS CLI to treat the path as a *prefix* rather
    than a single object. Without it, the command applies only to the object
    with that exact key, not to everything under the prefix.
  - When applying an operation to all objects under a prefix, also include
    ``--recursive``; otherwise, the command will not descend into the
    pseudo-directory.

Checking S3 Bucket Size (for FSx Planning)
--------------------------------------------------------

Before importing data from S3 into FSx, determine the **total logical size**
of the S3 bucket or prefix. This value should be used to size FSx storage.

Use the AWS CLI (recommended):
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

  aws s3 ls s3://dzhang-imi-gchp-test --recursive --summarize \
    | awk '/Total Size/ {printf "%.2f GB\n", $3/1024/1024/1024}' 

To check the size of a specific prefix (useful when multiple DRAs are used):

.. code-block:: bash

  aws s3 ls s3://dzhang-imi-gchp-test/ExtData --recursive --summarize \
    | awk '/Total Size/ {printf "%.2f GB\n", $3/1024/1024/1024}'
  aws s3 ls s3://dzhang-imi-gchp-test/blended-tropomi --recursive --summarize \
    | awk '/Total Size/ {printf "%.2f GB\n", $3/1024/1024/1024}'
  

Use the AWS console:
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. Go to your S3 bucket
2. Click on **Metrics** tab
3. Check **Total bucket size**


Notes and Best Practices
------------------------

- Prefer ``aws s3 sync`` for repeated uploads
- Keep S3 buckets private by default
- Upload data from the same AWS region whenever possible
- Use FSx DRA for high-throughput workflows
- Avoid browser uploads for large or critical datasets


Next Steps
----------

After uploading data, you may want to:

    - Configure bucket access policies for collaborators
    - Associate the bucket with FSx for Lustre
    - Automate uploads in batch or workflow scripts
