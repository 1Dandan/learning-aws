.. _pricing:

Cost considerations: S3 vs FSx for Lustre vs compute
------------------------------------------------------

When designing AWS workflows for data-intensive modeling (e.g., GEOS-Chem / GCHP),
it is important to distinguish **persistent storage**, **high-performance scratch storage**,
and **compute cost**, as they differ substantially in pricing and intended use.

High-level pricing overview
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The table below summarizes typical AWS costs relevant to data-intensive
HPC workflows. Prices are approximate and may vary by region, availability
zone, and market conditions.

.. list-table::
   :widths: 22 18 20 20
   :header-rows: 1

   * - Resource
     - Typical cost
     - Billing unit
     - Notes / intended use
   * - Amazon S3 Standard
     - ~$0.023
     - per GB-month
     - Lowest-cost persistent storage.
   * - FSx for Lustre (Scratch 2)
     - ~$0.140
     - per GB-month
     - High-performance parallel filesystem for runtime I/O.
       
       Significantly more expensive than S3; intended for short-lived use.
   * - EC2 Spot instances
     - ~$1
     - per node-hour
     - Compute cost usually dominates total spend.
       
       Price varies strongly by instance type and availability zone.

S3: lowest-cost persistent storage
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Amazon S3 is the most cost-effective option for long-term storage of model input data,
restart files, and archived outputs.

- **S3 Standard (active storage)** costs **$0.023 per GB-month**
  (`AWS S3 pricing <https://aws.amazon.com/s3/pricing/>`_).

- There is **no minimum storage duration** for S3 Standard.

- S3 is designed for **durability and scalability**, not low-latency parallel I/O,
  which makes it ideal as a *persistent data lake* rather than a runtime filesystem.

- Additional cost components to be aware of:
  
  - **Requests** (PUT, GET, LIST), which are typically negligible compared to storage
    for scientific workflows.
  - **Data transfer**:
    
    - Data transfer into S3 is free from local files or same-regions transfer.
    - Data transfer from S3 to EC2 or FSx within the same region is free
      (common case for HPC workflows).
    - Data transfer **out of AWS** (to the public internet) is charged.

FSx for Lustre: high-performance, higher-cost storage
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Amazon FSx for Lustre provides a **parallel POSIX filesystem** optimized for
high-throughput and low-latency I/O during model execution.

- **FSx for Lustre Scratch 2** costs approximately **$0.140 per GB-month**
  for provisioned storage
  (`AWS FSx for Lustre pricing <https://aws.amazon.com/fsx/lustre/pricing/>`_).

- FSx is intended for:
  
  - Runtime model input/output
  - Checkpointing
  - High-frequency parallel reads and writes

- FSx storage is **significantly more expensive than S3** and should therefore be
  treated as **temporary or performance-critical storage**, not long-term storage.

- FSx file systems can be linked to S3 using **Data Repository Associations (DRA)**,
  enabling data to be staged from S3 into FSx and written back when jobs complete.

Compute cost usually dominates overall spending
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For most HPC workloads, **compute cost dominates total cost**, while storage
(often S3) is comparatively cheap.

- Spot EC2 instances commonly cost **~$1 per node-hour**, depending on:
  
  - Instance type
  - Availability zone
  - Spot market conditions

- Pricing references:
  
  - `AWS EC2 Spot pricing <https://aws.amazon.com/ec2/spot/pricing/>`_
  - `Vantage instance price summary <https://instances.vantage.sh/>`_

As a result:

- **Reducing wall-clock runtime** (e.g., faster I/O using FSx) can save more money
  than minimizing storage costs.
- Paying for short-lived FSx storage is often justified if it substantially reduces
  expensive compute time.

Recommended cost-efficient pattern
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A common and cost-effective pattern is:

1. Store all persistent data (input datasets, restarts, archived outputs) in **S3**.
2. Stage required data from S3 to **FSx for Lustre** before or during job startup.
3. Run compute-intensive jobs using FSx for high-performance I/O.
4. Write final outputs back to S3.
5. Delete or reuse FSx file systems as needed to minimize storage duration.

This approach leverages the **low cost of S3**, the **performance of FSx**, and
acknowledges that **compute time is the primary cost driver** for large-scale
modeling workloads.
