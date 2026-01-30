AWS services and resources
==========================

An AWS service is a managed capability provided by AWS that exposes APIs to
perform a specific class of tasks on AWS resources.

We never directly interact with AWS services. Instead, we call AWS service
APIs to perform actions on resources.

An AWS resource is a concrete object created and managed by an AWS service.
Resources can be created, described, modified, and deleted via AWS APIs,
typically using the AWS Console, CLI tools, or SDKs (for example, the
``boto3`` Python package).

Examples of AWS resources
-------------------------

For example, an EC2 instance is an AWS resource managed by the EC2 service.
It can be:

- Created (``run-instances``)
- Described (``describe-instances``)
- Modified (``stop-instances`` / ``start-instances``)
- Deleted (``terminate-instances``)

Example AWS services and resources
----------------------------------

The table below summarizes common AWS services and the resources they manage.

=========================== ================== =====================================
Need                        AWS service        AWS resource
=========================== ================== =====================================
Virtual machines            EC2                Instances, AMIs, volumes, security groups
Object storage              S3                 Buckets, objects
File systems                FSx                File systems
Networking                  VPC                VPCs, subnets, route tables
Infrastructure automation   CloudFormation     Stacks
Identity & access            IAM                Users, roles, policies
Batch/HPC orchestration     ParallelCluster    (No native resources; orchestrates others)
Logs                         CloudWatch         Log groups, log streams, metrics, alarms
=========================== ================== =====================================

Miscellaneous clarifications
----------------------------

CloudFormation
~~~~~~~~~~~~~~

CloudFormation is a first-class AWS service that owns *stacks*.

A CloudFormation stack creates, updates, and deletes other AWS resources
defined in its template.

ParallelCluster
~~~~~~~~~~~~~~~

AWS ParallelCluster is not a resource-owning service by itself. Instead, it
is an orchestration tool that generates CloudFormation stacks to create and
manage an HPC cluster on AWS.

ParallelCluster operates on top of services such as CloudFormation, EC2,
IAM, FSx, and VPC.

VPC
~~~

Relationship between region, VPC, subnet, and availability zone (AZ):

- A region (for example, ``us-east-1``) can have many VPCs
- A VPC belongs to a specific region
- A subnet is a slice of a VPC’s IP address space and is associated with a
  single Availability Zone (for example, ``us-east-1a``)
- A VPC can contain many subnets

An EC2 instance (such as a head node or compute node) is launched into a
subnet and therefore physically resides in that subnet’s Availability Zone.

Although a region may contain many AZs, we typically specify a **subnet ID**
rather than an AZ directly, which implicitly selects the AZ.
