.. _fsx-s3-data-management:

Loading Data from S3 to FSx and Using S3 as Backup
==================================================

This section describes how to load data from Amazon S3 into an
FSx for Lustre file system using Data Repository Associations (DRA),
and presents a recommended strategy for using S3 as durable storage
to back up data when using **FSx scratch** file systems.

Background and Design Philosophy
--------------------------------

FSx for Lustre **scratch** file systems provide very high I/O performance
at low cost, but they are **not durable storage**:

- Scratch FSx does **not** replicate data
- Scratch FSx does **not** support backups
- Data loss is possible in the event of service or hardware failure

Therefore:

- **FSx scratch must never be treated as the only copy of important data**
- **Amazon S3 should be used as the authoritative source and/or backup**

The recommended design is:

- **Input data**: stored durably in S3, imported into FSx for fast access
- **Output data**: written to FSx during computation and exported back to S3

Data Repository Associations (DRA)
----------------------------------

A :ref:`Data Repository Association (DRA) <dra>` links a directory inside FSx to
an S3 bucket or prefix.

For example:

- FSx path ``/ExtData`` ↔ ``s3://my-bucket/ExtData/``
- FSx path ``/output``  ↔ ``s3://my-bucket/output/``

After mounting FSx locally at ``/fsx_input``, these appear as::

  /fsx_input/ExtData
  /fsx_input/output

A file system may have **multiple DRAs**, provided their FSx paths do
not overlap.

How Data Is Loaded from S3 to FSx
---------------------------------

It is important to understand that **creating a DRA does not immediately
copy all file contents from S3**.

By default:

- FSx does **not** proactively import metadata or file contents
- Metadata and data are imported **lazily** when files are accessed
- This behavior saves time and storage for large datasets

There are three ways to populate data from S3 to FSx.

Method 1: On-Demand Loading (Default)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If auto-import policies are enabled on the DRA:

- Files and directories appear immediately under FSx
- File contents are fetched automatically when first accessed

Example::

  ls /fsx-input/ExtData
  cat /fsx-input/ExtData/example.nc

This method is sufficient for most workflows and requires no manual action.

Method 2: Batch Metadata Import (Recommended After Creation)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To ensure the full directory structure appears immediately, run a
metadata import task.

Auto-import policies are enabled by default, you can check by:

  - Checking Auto-Import Policies via AWS Console

    1. Go to **AWS Console → FSx**
    2. Select your **FSx for Lustre** file system
    3. Open the **Data repository** tab
    4. In the **Data repository associations** table, check the **Import policy** column for each DRA

    Possible values include:

    - ``NEW, CHANGED, DELETED``  
      Auto-import is **enabled**. FSx will automatically detect new, modified,
      and deleted objects in the associated S3 path.

    - ``None`` or an empty value  
      Auto-import is **not enabled**. FSx will not automatically notice changes
      in S3.

- Checking Auto-Import Policies via AWS CLI

    You can also verify auto-import policies using the AWS CLI:

    .. code-block:: bash

        aws fsx describe-data-repository-associations

    For a more readable summary:

    .. code-block:: bash

        aws fsx describe-data-repository-associations \
            --query "Associations[*].{ \
            FSxPath:FileSystemPath, \
            ImportPolicy:S3.AutoImportPolicy.Events, \
            ExportPolicy:S3.AutoExportPolicy.Events \
            }"

    Example output::

        [
            {
            "FSxPath": "/ExtData",
            "ImportPolicy": ["NEW", "CHANGED", "DELETED"],
            "ExportPolicy": null
            },
            {
            "FSxPath": "/blended-tropomi",
            "ImportPolicy": ["NEW", "CHANGED", "DELETED"],
            "ExportPolicy": ["NEW", "CHANGED", "DELETED"]
            }
        ]

    Interpretation:

    - ``ImportPolicy`` containing one or more events (``NEW``, ``CHANGED``,
      ``DELETED``) indicates that **auto-import is enabled**
    - ``ImportPolicy = null`` indicates that **auto-import is disabled**
    - ``ExportPolicy`` shows whether automatic export (FSx → S3) is enabled

- What Auto-Import Policies Do (and Do Not Do)

    Auto-import policies provide the following behavior:

    - Changes in S3 are automatically detected
    - Directory structure and metadata in FSx are kept in sync
    - File contents are fetched **on demand** when accessed

    Auto-import policies **do not** guarantee that:

    - All file contents have already been copied to FSx
    - FSx remains usable if the S3 bucket is deleted

    To fully copy all data from S3 to FSx, an explicit
    ``IMPORT_FROM_REPOSITORY`` task must be executed.


    Example::

        aws fsx create-data-repository-task \
            --type IMPORT_METADATA_FROM_REPOSITORY \
            --file-system-id fs-xxxxxxxx \
            --paths /ExtData

    Repeat for other DRA paths as needed.

    This imports **only metadata**, not file contents.

Method 3: Full Data Import (Required Before Deleting S3)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you intend to delete the associated S3 bucket or make FSx
fully self-contained, you **must explicitly import all data**.

Example::

  aws fsx create-data-repository-task \
    --type IMPORT_FROM_REPOSITORY \
    --file-system-id fs-xxxxxxxx \
    --paths /ExtData

This command copies **all file contents** from S3 to FSx.

.. warning::

  Do **not** delete the S3 bucket until all
  ``IMPORT_FROM_REPOSITORY`` tasks complete successfully.
  DRA availability alone does not guarantee data has been copied.

Monitor progress with::

  aws fsx describe-data-repository-tasks

Proceed only when ``Lifecycle = COMPLETED``.

FSx Storage Capacity Considerations
-----------------------------------

When performing a full import:

- FSx storage capacity must be **greater than or equal to**
  the total logical size of data in S3 (Add some headroom is recommended)
- Do **not** rely on compression to reduce required capacity
- Imports will fail if FSx runs out of space

Recommended Backup Strategy Using S3
------------------------------------

The recommended and safe pattern for FSx scratch usage is:

Input Data (Read-Only)
^^^^^^^^^^^^^^^^^^^^^^

- **Authoritative copy**: S3
- **Working copy**: FSx scratch
- **DRA policy**:
  
  - Import: NEW, CHANGED, DELETED
  - Export: disabled

If FSx fails:

- Recreate FSx
- Re-import from S3
- No data loss

Output Data (Write-Back)
^^^^^^^^^^^^^^^^^^^^^^^^^^

- **Working location**: FSx scratch
- **Backup location**: S3 (separate bucket or prefix)
- **DRA policy**:
  - Export enabled (auto-export or manual)
- Output data is continuously or periodically written to S3

If FSx fails:
- Completed output already exists in S3
- Only in-progress work may be lost

.. note::

  S3 provides high durability at low cost and should always be used
  to store important or irreplaceable data when using FSx scratch.

When Is It Safe to Delete the S3 Bucket?
----------------------------------------

It is safe to delete the S3 bucket **only if all of the following are true**:

- Full ``IMPORT_FROM_REPOSITORY`` tasks have completed
- FSx storage usage is stable (verified with ``lfs df``)
- Files remain readable after cache drops
- You understand that FSx scratch provides no recovery or backups

In most cases, deleting the S3 bucket is **not recommended**.
Keeping S3 as the durable source of truth is safer and usually cheaper.

Summary
--------

- FSx scratch provides fast but non-durable storage
- DRA does not automatically copy all file contents
- Use explicit import tasks to fully populate FSx if needed
- Always use S3 as the durable source and/or backup
- Never treat FSx scratch as the only copy of important data
