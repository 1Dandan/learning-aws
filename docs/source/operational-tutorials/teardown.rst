Teardown and cleanup
===================

Always delete unused resources to avoid charges.

- **EC2 instances**

  - Stop instance still incur charges; 
  - If we do not need it, we can terminate (delete) it entirely to reduce cost


- **ParallelCluster**

.. code-block:: bash
    
    pcluster delete-cluster --cluster-name "my-cluster-name" --region "region-code"

