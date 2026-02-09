Create a ParallelCluster via AWS CLI
=====================================

Create the cluster
----------------------

.. code-block:: bash

   pcluster create-cluster -c <pcluster-create.yml> -n <cluster-name> -r <region>

Checklist for ``pcluster-create.yml``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- **Minimum required sections**
  
  - ``Region``, ``Image``, ``HeadNode``, and ``Scheduling`` (with ``SlurmQueues``).

- **SSH access**
  
  - Head node security group allows inbound **TCP 22** from your IP
    (or VPN / bastion).
  - ``HeadNode.Ssh.KeyName`` matches an existing EC2 key pair in the region.

- **Networking**
  
  - Head node subnet, compute subnets, and any FSx file system are in the
    same **VPC**.
  - Security groups referenced in the config belong to the same VPC.

- **Slurm queues**
  
  - Each queue in ``SlurmQueues`` has a unique ``Name``.
  - Each queue includes ``CapacityType``, ``Networking.SubnetIds``,
    and ``ComputeResources``.
  - Each compute resource specifies ``InstanceType`` and integer
    ``MinCount`` / ``MaxCount``.

- **IAM note (common failure point)**
  
  - The AWS identity used to run ``pcluster create-cluster`` must have
    permission to create and manage required resources
    (EC2, CloudFormation, IAM) and to **pass IAM roles**.
  - You can verify the active identity with:

    .. code-block:: bash

       aws sts get-caller-identity

Example ``pcluster-create.yml``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

An example :download:`pcluster-create.yml <../configs/pcluster-create.yml>`:

.. code-block:: yaml

   Region: us-east-1

   Image:
     Os: ubuntu2404
     CustomAmi: ami-08ea421ec9fad0a09

   HeadNode:
     InstanceType: c5.large
     Ssh:
       KeyName: dzhang  # <-- change to your keypair name
     Networking:
       SubnetId: subnet-08895ae58a2f9167d
       SecurityGroups:
         - sg-0f504cd36a5dc0b34

   Scheduling:
     Scheduler: slurm
     SlurmSettings:
       QueueUpdateStrategy: DRAIN
     SlurmQueues:
       - Name: ondemand
         CapacityType: ONDEMAND
         Networking:
           SubnetIds:
             - subnet-08895ae58a2f9167d
           SecurityGroups:
             - sg-0f504cd36a5dc0b34
         ComputeResources:
           - Name: c8a12xl
             InstanceType: c8a.12xlarge
             MinCount: 0
             MaxCount: 20

       - Name: spot
         CapacityType: SPOT
         Networking:
           SubnetIds:
             - subnet-08895ae58a2f9167d
           SecurityGroups:
             - sg-0f504cd36a5dc0b34
         ComputeResources:
           - Name: c8a12xl
             InstanceType: c8a.12xlarge
             MinCount: 0
             MaxCount: 50

   SharedStorage:
     - Name: fsx_input
       StorageType: FsxLustre
       MountDir: /fsx_input
       FsxLustreSettings:
         FileSystemId: fs-009ecfd7e44882657

Monitor the creation process
----------------------------

.. code-block:: bash

   pcluster describe-cluster -n <cluster-name> -r <region>

``clusterStatus``:

1. ``CREATE_IN_PROGRESS`` → normal
2. ``CREATE_COMPLETE`` → success
3. ``CREATE_FAILED`` → stop and debug

Delete ParallelCluster
----------------------

Delete by cluster name
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   pcluster delete-cluster -n <cluster-name> -r <region>

Find the cluster name (if forgotten)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If the head node still exists, you can infer the cluster name from the
head node IAM role in the EC2 console:
the string before ``-RoleHeadNode`` is typically the cluster name.

If the head node has already been deleted, list clusters in the region:

.. code-block:: bash

   pcluster list-clusters -r <region>

Then inspect a specific cluster:

.. code-block:: bash

   pcluster describe-cluster -n <cluster-name> -r <region>

Recover the configuration YAML used to create a cluster
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

From the output of ``pcluster describe-cluster``, look for:

.. code-block:: json

   "clusterConfiguration": {
     "url": "https://parallelcluster-.../clusters/<cluster-name>/configs/cluster-config.yaml?versionId=..."
   }

Download the configuration file:

.. code-block:: bash

   curl -o cluster-config.yaml "<that-URL>"
