Templates
=========

This page provides reusable YAML templates for common ACMG AWS workflows.

Template: AMI build configuration (ami-build.yaml)
--------------------------------------------------

This configuration is used by:

.. code-block:: bash

   pcluster build-image -c ami-build.yaml -i <image_id> -r <region>

Example template
^^^^^^^^^^^^^^^^

.. code-block:: yaml

   # ami-build.yaml
   # ParallelCluster Image Build configuration
   #
   # Usage:
   #   pcluster build-image -c ami-build.yaml -i <image_id> -r us-east-1
   #
   # Notes:
   # - SubnetId must be in the same region as the ParentImage
   # - Subnet should have internet egress (IGW or NAT) for package installation
   # - SecurityGroupIds should allow required outbound access for installation
   # - Use the correct Image.Os for your OS version (e.g., ubuntu2404)

   Region: us-east-1

   Image:
     Name: <your-image-name>            # e.g., gchp-imi-pcluster-base-v202601
     Os: ubuntu2404                     # e.g., ubuntu2204, ubuntu2404, alinux2, etc.

   Build:
     ParentImage: <parent-ami-id>       # e.g., ami-0f25a533d0bc938a8
     InstanceType: t3.large
     SubnetId: <subnet-id>              # e.g., subnet-xxxxxxxx
     SecurityGroupIds:
       - <security-group-id>            # e.g., sg-xxxxxxxx
     UpdateOsPackages:
       Enabled: true

Optional: Custom build steps
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you maintain bootstrap scripts or want custom packages installed during image
build, you can extend the build process using ParallelCluster-supported
custom actions. The exact mechanism varies by ParallelCluster version and your
preferred approach (pre-bake in ParentImage vs. install during build).



Template: Cluster configuration (pcluster-create.yml)
-----------------------------------------------------

This configuration is used by:

.. code-block:: bash

   pcluster create-cluster -c pcluster-create.yml -n <cluster-name> -r <region>

Example template (Slurm + FSx for Lustre)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: yaml

   # pcluster-create.yml
   # ParallelCluster cluster configuration (Slurm)
   #
   # Usage:
   #   pcluster create-cluster -c pcluster-create.yml -n <cluster-name> -r us-east-1
   #
   # Notes:
   # - SubnetId should be in the same VPC as your FSx filesystem if you will mount FSx
   # - Security groups must allow Lustre TCP 988 if mounting FSx for Lustre
   # - Choose instance types appropriate for your workload and budget

   Region: us-east-1

   Image:
     CustomAmi: <your-custom-ami-id>          # AMI built by pcluster build-image, or another suitable AMI

   HeadNode:
     InstanceType: t3.large
     Networking:
       SubnetId: <subnet-id>                 # e.g., subnet-xxxxxxxx
     Ssh:
       KeyName: <ec2-keypair-name>           # name of the EC2 key pair (not a local filename)
     # Optional: attach IAM policies/roles are typically managed by the account admins

   Scheduling:
     Scheduler: slurm
     SlurmSettings:
       QueueUpdateStrategy: DRAIN
     SlurmQueues:
       - Name: compute
         ComputeResources:
           - Name: c6i
             InstanceType: c6i.large
             MinCount: 0
             MaxCount: 10
         Networking:
           SubnetIds:
             - <subnet-id>                   # often same as HeadNode subnet
         # Optional: custom AMI is inherited from Image.CustomAmi unless overridden

   SharedStorage:
     # Option A: Use an existing FSx for Lustre filesystem (recommended when you already created FSx)
     - Name: fsx
       StorageType: FsxLustre
       MountDir: /fsx
       FsxLustreSettings:
         FileSystemId: <fsx-filesystem-id>   # e.g., fs-0123456789abcdef0

     # Option B (alternative): Use EBS as shared storage (not a Lustre filesystem)
     # - Name: shared-ebs
     #   StorageType: Ebs
     #   MountDir: /shared
     #   EbsSettings:
     #     VolumeType: gp3
     #     Size: 200

Common placeholders
^^^^^^^^^^^^^^^^^^^

Replace these placeholders with your values:

- ``<your-custom-ami-id>``: AMI ID to use for cluster nodes
- ``<subnet-id>``: Subnet ID in the target VPC/region
- ``<ec2-keypair-name>``: EC2 key pair *name* as shown in AWS Console (Key pairs)
- ``<fsx-filesystem-id>``: FSx for Lustre filesystem ID

Quick validation commands
^^^^^^^^^^^^^^^^^^^^^^^^^

Validate config (syntax and some semantics):

.. code-block:: bash

   pcluster validate-configuration -c pcluster-create.yml -r us-east-1

Check cluster status:

.. code-block:: bash

   pcluster describe-cluster -n <cluster-name> -r us-east-1
