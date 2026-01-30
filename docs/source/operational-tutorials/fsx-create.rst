Create FSx filesystem
=====================

This section describes how to create an Amazon FSx for Lustre file system,
and how to mount it on an EC2 instance for use in computation workflows.

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
  
  - You may use default settings initially.
  - The FSx file system and any EC2 instances that mount it must be in the **same VPC**.
  - The associated security group must allow **TCP port 988** (Lustre).

- **Data repository import/export**  
  
  This option enables data synchronization between S3 and FSx through **data repository association (DRA)**.

Creation may take some time to complete.

Delete FSx
^^^^^^^^^^

To delete an FSx file system:

- Go to **FSx** in the AWS console
- Select the file system
- Choose **Actions → Delete file system**


Useful commands
-------------------

Describe FSx file systems using the AWS CLI:

.. code-block:: bash

   aws fsx describe-file-systems \
     --file-system-ids <file_system_id1> <file_system_id2> ...


Mount FSx to an EC2 instance
--------------------------------

Launch an EC2 instance
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Launch an EC2 instance with:

- The **same VPC** (and usually the same subnet) as the FSx file system
- A security group that allows **TCP port 988 (Lustre)**

Lustre client utilities
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The Lustre client version on the EC2 instance must match the FSx server’s
supported client ABI.

In practice, this means using the same Lustre **major/minor series**
(for example, ``2.10 ↔ 2.10`` or ``2.15 ↔ 2.15``).

Verify Lustre installation
~~~~~~~~~~~~~~~~~~~~~~~~~~

Lustre client utilities are often installed by default. Verify by running:

.. code-block:: bash

   lfs --version
   lctl --version
   modinfo lustre

Install Lustre client on Ubuntu (if not installed)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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

Create a mount point (the directory name is arbitrary):

.. code-block:: bash

   sudo mkdir -p /fsx

Mount the FSx file system:

.. code-block:: bash

   sudo mount -t lustre -o relatime,flock \
     <fsx-dns-name>@tcp:/<fsx-mount-name> \
     <local-mount-point>

For example:

.. code-block:: bash

   sudo mount -t lustre -o relatime,flock \
     fs-0123456789abcdef.fsx.us-east-1.amazonaws.com@tcp:/fsx \
     /fsx

Debug mount failure
~~~~~~~~~~~~~~~~~~~

If mounting fails, check the kernel messages immediately after the failure:

.. code-block:: bash

   sudo dmesg | egrep -i 'lustre|lnet|mgc|lmgs' | tail -n 60
