AWS account setup
=================

This section describes how to set up AWS access for users in the Harvard ACMG
AWS environment, including SSH key pairs, IAM users, credentials, and
advanced administrative workflows.

SSO login
-----------------------------

Contact HUIT for an AWS account.

Login AWS console with Harvard key access.

Create and store key pair
-----------------------------

Login to the AWS Management Console using your Harvard ID.

In the AWS console search bar:

- Search for **Key pairs**
- Click **Create key pair** (yellow button on the right)
- Enter a key pair name
- Select key pair type **ED25519** (recommended; more modern than RSA)
- Leave the key file format as default

Store the key pair
^^^^^^^^^^^^^^^^^^

The private key file can only be downloaded **once at creation time**.
Make sure to store it in a secure location.

Change the permission of the key file:

.. code-block:: bash

   chmod 400 <your_key_pair_name>.pem

This permission setting is required for AWS SSH usage.


AWS configure (IAM user)
----------------------------

Create IAM user
^^^^^^^^^^^^^^^^^^^^

In the AWS Management Console:

- Search for **IAM**
- On the left-hand menu, select **Users**
- Click **Create user**

Add proper permissions
^^^^^^^^^^^^^^^^^^^^^^

ACMG users are granted permissions through an existing IAM user group.

The current user group **LAE-gcst-policy-group** already has the required
permissions. Simply add the newly created IAM user to this group.


Create access key
^^^^^^^^^^^^^^^^^^^^^^

From the IAM console:

- Select your **user name** (for example, ``dzhang``)
- Click **Create access key**

You will be presented with an **Access key ID** and **Secret access key**.

.. important::

   This is the only time the secret access key can be viewed or downloaded.
   Leave this page open or download the CSV file. The secret access key
   is required for AWS CLI configuration.


Configure AWS with IAM user credential
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Configure AWS credentials by running:

.. code-block:: bash

   aws configure

Provide the following information when prompted:

- **AWS Access Key ID**  
  Enter the access key of the IAM user
- **AWS Secret Access Key**  
  Enter the secret access key of the IAM user
- **Default region name**  
  ``us-east-1``
- **Default output format**  
  ``json``

Notes
^^^^^

- ``aws configure`` writes config and credentials to:

  - ``~/.aws/config``
  - ``~/.aws/credentials``

- Additional IAM user credentials can be added later by editing
  ``~/.aws/credentials`` directly.

- When using the AWS CLI, a specific credential profile can be selected with:

  .. code-block:: bash

     --profile <credential_name>

- The credential name does not need to match the IAM user name. It is defined
  in ``~/.aws/credentials``.


(Advanced / emergency) Temporary admin IAM user
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In organization-managed AWS accounts, certain IAM policies are enforced
through groups or Service Control Policies (SCPs) and cannot be modified
by standard users or SSO roles.

Although we can attach IAM permission policies to a normal IAM user, some
policies cannot be detached. In addition, AWS enforces a hard limit of
10 attached policies per IAM user.

In these situations, it may be necessary to create a **temporary admin IAM
user**.

Create an admin IAM user
^^^^^^^^^^^^^^^^^^^^^^^^

The user creation process is the same as for a regular IAM user, except that
in **Set permissions**, select:

- **Attach policies directly**
- Choose **AdministratorAccess**

This grants full administrative access to the user.

Create access key for admin user
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

- Click the admin IAM user
- Create an access key
- Add the access key and secret access key to ``~/.aws/credentials``

Use the same format as the default user, but give the profile a different name,
for example [acmg_admin]

Using admin to detach or delete IAM permission policies
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Check IAM policies directly attached to a user:

.. code-block:: bash

   aws iam list-attached-user-policies \
     --profile acmg_admin \
     --user-name dzhang \
     --query "AttachedPolicies[*].[PolicyName,PolicyArn]" \
     --output table

Detach an IAM permission policy directly attached to a user:

.. code-block:: bash

   aws iam detach-user-policy \
     --user-name <USER_NAME> \
     --profile <admin_name> \
     --policy-arn <POLICY_ARN>

Notes:

- IAM policies attached **through a user group** (for example,
  ``LAE-gcst-policy-group``) cannot be detached from the user directly.
- Inline policies can be deleted using:

  .. code-block:: bash

     aws iam delete-user-policy \
       --user-name <user_name> \
       --policy-name <policy_name>


Deactivate access key for admin IAM user
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

An admin IAM user has nearly full access to AWS resources. To reduce security
risk, the access key for an admin IAM user should be **deactivated immediately
after use**.

To deactivate the access key:

- Go to the AWS Management Console
- Select the admin IAM user
- Open **Security credentials**
- Scroll to the **Access keys** section
- Select **Actions**
- Choose **Deactivate**

The key can be reactivated later if needed.
