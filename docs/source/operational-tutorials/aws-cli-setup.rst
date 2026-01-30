AWS utilities
====================================

This page describes how to install the AWS Command Line Interface (CLI) and
the AWS ParallelCluster CLI, which are required to interact with AWS services
and create HPC clusters programmatically.

Official installation instructions
----------------------------------

The authoritative installation guides are maintained by AWS:

- **AWS CLI**  
  https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html

- **AWS ParallelCluster CLI**  
  https://docs.aws.amazon.com/parallelcluster/latest/ug/install-v3-parallelcluster.html

These instructions should be consulted for platform-specific details and
the most up-to-date guidance.

Install using conda or mamba
----------------------------

For users who manage Python environments with ``conda`` or ``mamba``, it is
often convenient to install the CLI tools in an isolated environment.

First, activate your conda or mamba installation:

.. code-block:: bash

   source /your_conda_dir/bin/activate

Create and activate a new environment:

.. code-block:: bash

   conda create -n aws
   conda activate aws

Install the AWS CLI:

.. code-block:: bash

   conda install awscli

Install the ParallelCluster CLI using ``pip``:

.. code-block:: bash

   pip install "aws-parallelcluster"

Using a dedicated environment helps avoid dependency conflicts with other
projects.

Confirm installation
--------------------

Verify that both tools are available:

.. code-block:: bash

   aws --version
   pcluster version

Successful execution of these commands should print the installed versions
of the AWS CLI and ParallelCluster CLI.

If either command fails, ensure that the correct environment is activated
and that the installation completed without errors.
