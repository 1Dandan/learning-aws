.. _fsx:

Create an FSx file system
=========================

This section describes how to create an Amazon FSx for Lustre file system,
and how to mount it on an EC2 instance for use in computation workflows.

There are two ways to create an FSx file system to be used in ParallelCluster:

- **Internal FSx**

  We can create an FSx file system using a ParallelCluster creation YAML file.
  In this case, the FSx file system is tied to the cluster lifecycle, and
  ``DeletionPolicy`` must be explicitly specified.

  .. code-block:: yaml

    SharedStorage:
      - Name: fsx-lustre
        StorageType: FsxLustre
        MountDir: /fsx_input
        DeletionPolicy: Retain
        FsxLustreSettings:
          DeploymentType: SCRATCH_2

- **External FSx** (Recommended)

  We create an FSx file system independently, and ParallelCluster only mounts
  the existing file system. ParallelCluster will not delete it, since it is
  external to the cluster.

  Mounting can be specified in the ParallelCluster creation YAML file:

  .. code-block:: yaml

    SharedStorage:
      - MountDir: /fsx_input
        Name: fsx
        StorageType: FsxLustre
        FsxLustreSettings:
          FileSystemId: fs-XXXXXXXXXXXXXXXXX  # Replace with your actual FSx ID

  The FSx file system itself can be created through the AWS Console or AWS CLI.

.. _fsx-console:

Create FSx through AWS Console
------------------------------

Log in to the AWS Management Console.

In the console search bar:

- Search for **FSx**
- Select **Create file system**
- Choose **Amazon FSx for Lustre**

Specify file system details
^^^^^^^^^^^^^^^^^^^^^^^^^^^

When creating the file system, specify the following:

- **File system name**

  Choose a descriptive name for the FSx file system.

- **Data compression type**

  Choose the default compression type **LZ4**.

- **Deployment and storage class**

  Use **Scratch** to reduce cost for temporary or intermediate data.

- **Network and security**

  - You may use ``benchmarks-cloud-vpc`` for the VPC and
    ``benchmarks-cloud-sg`` for the security group initially, which already
    contains appropriate rules for Lustre access.
  - The FSx file system and any EC2 instances that mount it must be in the
    **same VPC**.
  - The associated security group must allow **TCP port 988** (Lustre).


Creation may take several minutes (typically ~7 minutes).

.. note::

  - **Recommendation:** Enable **LZ4 data compression** for FSx for Lustre by
    default. It is transparent, lossless, cost-reducing, and typically neutral
    or beneficial for I/O performance in scientific and HPC workloads.

  - When multiple security groups are attached to an FSx file system, inbound
    access is allowed if it matches any rule in any attached security group.
    **Security groups are additive, not restrictive**.

Delete FSx
^^^^^^^^^^^^^

To delete an FSx file system:

- Go to **FSx** in the AWS console
- Select the file system
- Choose **Actions → Delete file system**

Create FSx through AWS CLI
--------------------------

We can also use AWS CLI for reproducibility and automation.

The following example creates an FSx for Lustre file system **without**
any data repository associations:

.. code-block:: bash

  aws fsx create-file-system \
    --file-system-type LUSTRE \
    --storage-capacity 1200 \
    --subnet-ids subnet-xxxxxxxx \
    --security-group-ids sg-xxxxxxxx \
    --lustre-configuration \
      DeploymentType=SCRATCH_2,DataCompressionType=LZ4 \
    --tags Key=Name,Value=gchp-fsx-scratch

Monitor the creation process:

.. code-block:: bash

  aws fsx describe-file-systems \
    --query 'FileSystems[*].{ID:FileSystemId,State:Lifecycle,MountName:LustreConfiguration.MountName}'

Wait until ``Lifecycle = AVAILABLE``.

Delete the file system
^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

  aws fsx delete-file-system \
    --file-system-id fs-xxxxxxxx

Monitor deletion:

.. code-block:: bash

  aws fsx describe-file-systems \
    --file-system-ids fs-xxxxxxxx

When the file system is fully deleted, the command will return a
non-existing resource error.

Mount FSx to an EC2 instance
----------------------------

Prerequisites
^^^^^^^^^^^^^

- Launch an EC2 instance with:

  - The **same VPC** (and usually the same subnet) as the FSx file system
  - A security group that allows **TCP port 988 (Lustre)**

- Lustre client utilities

  The Lustre client version on the EC2 instance must match the FSx server’s
  supported client ABI.

  In practice, this means using the same Lustre **major/minor series**
  (for example, ``2.10 ↔ 2.10`` or ``2.15 ↔ 2.15``).

  Verify Lustre installation:

  .. code-block:: bash

    lfs --version
    lctl --version
    modinfo lustre

  Install Lustre client on Ubuntu (if not installed):

  .. code-block:: bash

    sudo apt update
    sudo apt install -y \
      linux-image-$(uname -r) \
      lustre-client-modules-$(uname -r) \
      lustre-client-utils
    sudo modprobe lustre

Mounting FSx to an EC2 instance
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Create a mount point:

  .. code-block:: bash

    sudo mkdir -p /fsx_input

- Mount the FSx file system:

  .. code-block:: bash

    sudo mount -t lustre -o relatime,flock,_netdev \
      <fsx-dns-name>@tcp:/<fsx-mount-name> \
      /fsx_input

  Example:

  .. code-block:: bash

    sudo mount -t lustre -o relatime,flock,_netdev \
      fs-0123456789abcdef.fsx.us-east-1.amazonaws.com@tcp:/fsx \
      /fsx_input

- Debug mount failure:

  .. code-block:: bash

    sudo dmesg | egrep -i 'lustre|lnet|mgc|lmgs' | tail -n 60

Change ownership for write permissions (FSx output data)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- By default, the root directory of a newly created FSx file system is owned by
  ``root:root``.
- The default permissions allow read access, so the file system can be used
  directly for read-only input data (e.g., ``/ExtData``).
- To allow non-root write access (for example, from ParallelCluster compute jobs),
  change the ownership of the FSx root or a designated output directory to a
  regular Linux user (e.g., ``ubuntu``).
- Permission changes made on a mounted FSx file system persist across future
  mounts and clusters.

- **Special case: Data Repository Association (DRA)**

  Files and directories imported from S3 via DRA are owned by ``root:root``.
  This is expected behavior because the transfer is performed by the FSx service
  rather than a Linux user.

- When data is transferred from S3 to FSx using ``aws s3 sync`` or ``aws s3 cp``
  on an EC2 instance, files inherit the ownership of the Linux user running the
  command, subject to parent directory permissions.

.. warning::

  Avoid modifying ownership or permissions on directories managed by
  Data Repository Associations unless you fully understand the implications.
  Subsequent DRA imports may reset ownership to ``root:root``.

Change ownership and permissions:

.. code-block:: bash

  # os-login-name depends on the OS (e.g., ubuntu, ec2-user)
  sudo chown <os-login-name>:<os-login-name> /fsx_input
  sudo chmod 2775 /fsx_input

.. note::

  Perform permission changes **after** successfully mounting FSx, so that
  changes apply to the FSx file system itself rather than the local mount point.