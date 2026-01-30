Overview: How AWS works
=======================

This page provides a high-level understanding of how AWS is used in this
project, before diving into specific concepts such as IAM identities,
APIs, services, and resources.

High-level workflow
-------------------

We use AWS credentials derived from an IAM identity (either an assumed IAM
role via Single Sign-On (SSO) or an IAM user with attached permission
policies) to call AWS service APIs.

Examples of AWS service APIs include:

- EC2
- FSx
- S3
- CloudFormation

These API calls create, modify, and manage AWS resources, such as:

- VPCs and subnets
- EC2 instances
- FSx file systems
- Amazon Machine Images (AMIs)

On AWS, **all infrastructure provisioning and management operations are
ultimately performed via AWS APIs**, regardless of whether the interaction
happens through the AWS Management Console, AWS CLI, or SDKs.

What this means in practice
---------------------------

From a practical perspective:

- Your **credentials** determine *who you are*
- IAM **policies and roles** determine *what APIs you are allowed to call*
- AWS **resources** are the objects those APIs act on

Tools such as the AWS Console, AWS CLI, and ParallelCluster are simply
different interfaces for issuing the same underlying API calls.

How this documentation is organized
-----------------------------------

This documentation is organized to follow the mental model above:

- **IAM identity**  
  Explains where credentials come from and how identities are defined

- **AWS APIs**  
  Explains how permissions are evaluated and how to reason about allowed
  actions

- **AWS services and resources**  
  Explains what services exist and what concrete resources they manage

The operational tutorials then build on this foundation to show how these
concepts are applied in practice.
