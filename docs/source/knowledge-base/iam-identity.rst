IAM identity
============

AWS credentials are derived from IAM identities, including IAM users and IAM
roles.

IAM users use long-term credentials, while IAM roles are accessed via
temporary STS credentials. Federated identities such as SSO users obtain
credentials by assuming IAM roles.

IAM user
--------

An IAM user is an IAM identity with credentials authorized by access keys,
which are commonly used with AWS CLI tools.

An IAM user represents a long-term identity within an AWS account. It has
long-lived access keys, which are configured via ``aws configure`` and used
by AWS CLI tools.

Permissions are attached directly to the IAM user or via IAM groups, and the
credentials remain valid until they are rotated or deleted.

IAM role
--------

An IAM role is an IAM identity with a set of permissions that can be
temporarily assumed by a trusted identity.

IAM roles do not have long-lived credentials. Instead, temporary credentials
are issued by AWS Security Token Service (STS) when the role is assumed.

Assumed IAM role via Single Sign-On (SSO)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Single Sign-On (SSO) is a federated authentication mechanism used to log in to
AWS via the link provided by HUIT.

After authentication, AWS IAM Identity Center assumes an IAM role on behalf
of the user and issues temporary STS credentials. These credentials are then
used to access the AWS Management Console and AWS APIs.

After logging in to the AWS console, you can view your account details in the
top-right corner. You may see an identity string similar to:

::

   acmgjacob-prod-standard-saml-poweruser-iam-role@us-east-1/dzhang@seas.harvard.edu

Where:

- **Federated user**: authentication via an external identity provider (SSO)
- **SAML**: SAML-based SSO
- **Poweruser**: SSO permission set
- **iam-role**: an IAM role assumed via SSO instead of an IAM user
- **dzhang@seas.harvard.edu**: specific user identity

Miscellaneous IAM roles
~~~~~~~~~~~~~~~~~~~~~~~

An IAM role can be assumed by a variety of trusted identities, including:

- AWS SSO users
- IAM users
- EC2 instances
- Lambda functions

Permission policies define which AWS APIs are allowed to be called and on
which resources while assuming the role.

Permissions are specified using the format:

::

   <service>:<Action> on <resource ARN>

Examples include:

- ``ec2:CreateImage``
- ``fsx:CreateFileSystem``
- ``cloudformation:*``

A *resource* is an AWS object that an API action acts on, identified by an
Amazon Resource Name (ARN). Examples include an EC2 instance, an AMI, a
subnet, or a security group.

IAM roles in ParallelCluster
----------------------------

In AWS ParallelCluster, there are two important IAM roles:

Head node IAM role
~~~~~~~~~~~~~~~~~~

- An IAM role attached to the head node EC2 instance
- Typical responsibilities include:
  - Describing and managing EC2 and Auto Scaling resources
  - Launching and terminating compute nodes
  - Managing cluster infrastructure required by Slurm
  - Writing logs and metrics to CloudWatch

Compute node IAM role
~~~~~~~~~~~~~~~~~~~~~

- An IAM role attached to each compute node EC2 instance
- The role is inherited by jobs running on the compute node **only for AWS
  API calls** made by the job or associated scripts

Data access considerations
^^^^^^^^^^^^^^^^^^^^^^^^^^

FSx access
~~~~~~~~~~

FSx is a POSIX file system. Reading from and writing to FSx is handled at the
OS and file-system level and does not involve AWS APIs.

Therefore, no special IAM permissions are required on the compute node IAM
role for normal FSx file I/O.

S3 access
~~~~~~~~~

Amazon S3 is an AWS-managed resource. Any data transfer between FSx and S3
(for example, ``aws s3 cp`` or ``aws s3 sync``) is performed via AWS APIs.

Consequently, the compute node IAM role (or another EC2 instance role used
for offline transfer) must include the appropriate S3 permissions to allow
these operations.
