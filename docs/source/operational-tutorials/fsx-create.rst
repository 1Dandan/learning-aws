.. _fsx:

Create a FSx filesystem
==========================

This section describes how to create an Amazon FSx for Lustre file system,
and how to mount it on an EC2 instance for use in computation workflows.

There are two ways to create FSx filesystem to be used in ParallelCluster:

- **Internal FSx**
  
  We can create an FSx using a pcluster creation yaml file, but
  in that case the FSx would be tied to the pcluster, and we need to define ``DeletionPolicy``

  .. code-block:: yaml

    SharedStorage:
      - Name: fsx-lustre
        StorageType: FsxLustre
        MountDir: /fsx
        DeletionPolicy: Retain
        FsxLustreSettings:
          DeploymentType: SCRATCH_2

- **External FSx** (Recommended)
  
  We create an FSx filesystem first and ParallelCluster just mounts the existing FSx. 
  ParallelCluster will not delete it as it is external.

  Mounting can be specified in the ParallelCluster creation yaml file:

  .. code-block:: yaml

    SharedStorage:
      - MountDir: /ExtData # The desired mount point
        Name: fsx # The key name for the existing FSx file system
        StorageType: FsxLustre # Or FsxOntap, FsxOpenZfs
        FsxLustreSettings:
          FileSystemId: fs-XXXXXXXXXXXXXXXXX # Replace with your actual File System ID

  The creation (AWS APIs) can be called through AWS console or CLI.

.. _fsx-console:

Create FSx through AWS Console
---------------------------------

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

- **Deployment and storage class**  
  
  Use **Scratch** to reduce cost for temporary or intermediate data.

- **Network and security**  
  
  - You may use ``benchmarks-cloud-vpc`` for VPC and ``benchmarks-cloud-sg`` for security group initially, 
    which contains proper traffic for accessing Lustre. Subnet can leave as default.
  - The FSx file system and any EC2 instances that mount it must be in the **same VPC**.
  - The associated security group must allow **TCP port 988** (Lustre).

- **Data repository import/export**  
  
  This option enables data synchronization between S3 and FSx through :ref:`data repository association (DRA) <dra>`.

Creation may take some time (~7 mins) to complete.

Delete FSx
^^^^^^^^^^

To delete an FSx file system:

- Go to **FSx** in the AWS console
- Select the file system
- Choose **Actions → Delete file system**


Create FSx through AWS CLI
---------------------------------

We can also use AWS CLI for reproducibility and automation. 

The above creation example can be achieved by AWS CLI:

.. code-block:: bash

  aws fsx create-file-system \
    --file-system-type LUSTRE \
    --storage-capacity 1200 \
    --subnet-ids subnet-xxxxxxxx \
    --security-group-ids sg-xxxxxxxx \
    --lustre-configuration DeploymentType=SCRATCH_2 \
    --tags Key=Name,Value=gchp-fsx-scratch


And then we can monitor the creation process by:

.. code-block:: bash

  aws fsx describe-file-systems \
    --query 'FileSystems[*].{ID:FileSystemId,State:Lifecycle,MountName:LustreConfiguration.MountName}'


Wait until: ``Lifecycle = AVAILABLE``


We can delete an FSx system by:

.. code-block:: bash

  aws fsx delete-file-system \
    --file-system-id fs-xxxxxxxx

Monitoring the deletion process:

.. code-block:: bash
  
  aws fsx describe-file-systems \
    --file-system-ids fs-xxxxxxxx

Printing ``Lifecycle = DELETING``

Once it was deleted, you should see non-existing error from above command.

Mount FSx to an EC2 instance
--------------------------------

Prerequisites
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Launch an EC2 instance with:

  - The **same VPC** (and usually the same subnet) as the FSx file system
  - A security group that allows **TCP port 988 (Lustre)**


- Lustre client utilities

  The Lustre client version on the EC2 instance must match the FSx server’s
  supported client ABI.

  In practice, this means using the same Lustre **major/minor series**
  (for example, ``2.10 ↔ 2.10`` or ``2.15 ↔ 2.15``).

  - Verify Lustre installation

    Lustre client utilities are often installed by default. Verify by running either one of:

    .. code-block:: bash

      lfs --version
      lctl --version
      modinfo lustre

  - Install Lustre client on Ubuntu (if not installed)

    If Lustre is not installed, install it on Ubuntu using:

    .. code-block:: bash

      sudo apt update
      sudo apt install -y \
        linux-image-$(uname -r) \
        lustre-client-modules-$(uname -r) \
        lustre-client-utils
      sudo modprobe lustre


Mounting FSx to EC2 instance
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Create a mount point (the directory name is arbitrary)

  .. code-block:: bash

    sudo mkdir -p /fsx

- Mount the FSx file system

  .. code-block:: bash

    sudo mount -t lustre -o relatime,flock \
      <fsx-dns-name>@tcp:/<fsx-mount-name> \
      <local-mount-point>

  For example:

  .. code-block:: bash

    sudo mount -t lustre -o relatime,flock \
      fs-0123456789abcdef.fsx.us-east-1.amazonaws.com@tcp:/fsx \
      /fsx

- Debug mount failure

  If mounting fails, check the kernel messages immediately after the failure:

  .. code-block:: bash

    sudo dmesg | egrep -i 'lustre|lnet|mgc|lmgs' | tail -n 60


Change the ownership for writing permission (FSx for output data)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- By default, the root directory of a newly created FSx file system is owned by ``root:root``.
- The default permissions allow read access, so the filesystem can be used directly for read-only input data (e.g., ``/ExtData``).
- To allow non-root write access (for example, from ``ParallelCluster`` compute jobs), 
  we change the ownership of the filesystem root (or a designated output directory) to **a regular Linux user** (e.g. ``ubuntu``).
- After an FSx file system is mounted on an EC2 instance, 
  changing ownership or permissions on the mount point modifies the FSx file system itself, 
  and the changes persist across future mounts and clusters.
- **Special case Data Repository Association (DRA)**:
  When data is imported from S3 to FSx using DRA, 
  the files and directories created on FSx are owned by ``root:root``. 
  This is expected behavior, because the transfer is performed by the FSx service rather than a Linux user.
- When data is transferred from S3 to FSx using ``aws s3 sync`` or ``aws s3 cp`` on an EC2 instance, 
  the files are created by the Linux process running on that instance and therefore inherit the ownership of the regular Linux user, 
  subject to the permissions of the parent directory.

We can change the ownership and permissions by:

.. code-block:: bash

  # os-login-name depends on the OS, e.g. ubuntu for Ubuntu, ec2-user for Amazon Linux, etc.
  sudo chown <os-login-name>:<os-login-name> <local-mount-point>
  sudo chmod 2775 <local-mount-point>

.. note::

  We need to modify these after successful mounting, 
  so that changes are applied to the FSx file system itself, not the local mounting point.
