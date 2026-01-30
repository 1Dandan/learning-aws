Quickstart overview
===================

This section outlines the typical end-to-end workflow for running research
computations on AWS using preconfigured infrastructure.

High-level workflow
-------------------

1. Authenticate to AWS using SSO or credentials
2. Install and configure the AWS CLI
3. Build or select a custom AMI
4. Create a ParallelCluster
5. Attach shared storage (FSx)
6. Stage input data
7. Run workloads
8. Export results to S3
9. Tear down resources

Each step is described in detail in subsequent tutorials.

Assumptions
-----------

This documentation assumes:

- You have access to an AWS account
- You are permitted to create EC2, FSx, and CloudFormation resources (Check IAM permission policies)
- You are working in a Unix-like environment (Linux or macOS)
