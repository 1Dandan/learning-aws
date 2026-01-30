Creating Amazon Machine Image
=============================

An Amazon Machine Image (AMI) defines the software environment used by EC2
instances. It contains the operating system, libraries, and tools required for
workflows such as GCHP simulations and Python-based analysis.

Create AMI from AWS Console
-------------------------------

Launch an EC2 instance using a default AMI provided by Amazon with your
preferred operating system (for example, Amazon Linux or Ubuntu).

SSH into the instance:

.. code-block:: bash

   ssh -i <key_pair_path> <os_login_name>@<public_ip_address>

Notes:

- ``os_login_name`` depends on the operating system.
  For example:

  - ``ec2-user`` for Amazon Linux
  - ``ubuntu`` for Ubuntu

  (google search for confirmation)

- ``public_ip_address`` is the public IPv4 address shown in the AWS console
  for the EC2 instance.

Install required libraries
^^^^^^^^^^^^^^^^^^^^^^^^^^

Install all required libraries and tools directly on the EC2 instance,
following the same procedure as on a local machine running the same OS.

Create AMI
^^^^^^^^^^

Once configuration is complete, create an AMI from the EC2 instance using
the AWS console.

.. note::

   If the AMI will later be used with AWS ParallelCluster, the image must
   ultimately be built using ``pcluster``. Creating an AMI directly from
   the console is suitable only for intermediate or exploratory use.


Build AMI with ParallelCluster based on an existing AMI
------------------------------------------------------------

Prerequisites
^^^^^^^^^^^^^^^^^^^

IAM permissions
~~~~~~~~~~~~~~~

To build an AMI using ParallelCluster, the IAM user or role must include the
following permissions:

- ``AWSLambda_FullAccess``
- ``AmazonSNSFullAccess``

These permissions are required for image build workflows.

Check OS version
~~~~~~~~~~~~~~~~

When SSHing into an EC2 instance launched from the parent AMI, check the OS
version:

.. code-block:: bash

   cat /etc/os-release

The value of ``Image.Os`` used later must correspond to the operating system
version of the parent AMI.

Rules and supported values can be found at:

https://docs.aws.amazon.com/parallelcluster/latest/ug/Image-v3.html

For Ubuntu 24.04, use ``ubuntu2404`` 
as the ``Image.Os`` value.

Build process
-------------------

Create a configuration YAML file for image building
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Subnet requirements
~~~~~~~~~~~~~~~~~~~

- The subnet ID must be in the **same region** (for example, ``us-east-1``)
  as the parent AMI.
- The subnet must have **internet egress** (via an Internet Gateway or NAT)
  so the build process can install and configure required components.

VPC note
~~~~~~~~

It is not necessary to explicitly specify a VPC, since each subnet belongs
to exactly one VPC.

Example ``image-build.yaml``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   Region: us-east-1

   Image:
     Name: gchp-imi-pcluster-base-v202601

   Build:
     ParentImage: ami-0f25a533d0bc938a8   # existing AMI
     InstanceType: t3.large
     SubnetId: subnet-3198906c            # any suitable public subnet
     SecurityGroupIds:
       - sg-0b7fdbbcb20e53b4e
     UpdateOsPackages:
       Enabled: true


Run the image build
^^^^^^^^^^^^^^^^^^^^^^^^^^

Run the build using the ParallelCluster CLI:

.. code-block:: bash

   pcluster build-image \
     -c <image-config.yaml> \
     -i <image_id>

Notes:

- The ``-i <image_id>`` argument is still required.
- ``<image_id>`` can be the same string as the image name defined in
  ``image-build.yaml``.

Monitor build progress
^^^^^^^^^^^^^^^^^^^^^^

Check the image build status using:

.. code-block:: bash

   pcluster describe-image \
     -i gchp-imi-pcluster-base-v1 \
     -r us-east-1 \
     --query "imageBuildStatus"


Debug build failure
------------------------

If the image build fails, detailed error messages can be retrieved using
AWS CloudFormation:

.. code-block:: bash

   aws cloudformation describe-stack-events \
     --region us-east-1 \
     --stack-name gchp-imi-pcluster-base-v1 \
     --query "StackEvents[?ResourceStatus=='CREATE_FAILED'].[Timestamp,LogicalResourceId,ResourceType,ResourceStatusReason]" \
     --output table
