#!/bin/bash

REGION=us-east-1
TARGET_CAPACITY=96 # number of vCPUs

INSTANCE_TYPES=(
  c5.24xlarge
  c6i.24xlarge
  c7i.24xlarge
  c8i.24xlarge
)

spot_file=$(mktemp)
az_file=$(mktemp)

aws ec2 get-spot-placement-scores \
  --region "$REGION" \
  --instance-types "${INSTANCE_TYPES[@]}" \
  --target-capacity "$TARGET_CAPACITY" \
  --target-capacity-unit-type vcpu \
  --single-availability-zone \
  --region-names "$REGION" \
  --output json > "$spot_file"

aws ec2 describe-availability-zones \
  --region "$REGION" \
  --query "AvailabilityZones[?ZoneType=='availability-zone'].{AZName:ZoneName,AZID:ZoneId}" \
  --output json > "$az_file"

{
  printf "Region\tAZID\tAZName\tScore\n"
  jq -r '
    INDEX(input[]; .AZID) as $azmap
    | .SpotPlacementScores[]
    | [.Region, .AvailabilityZoneId, ($azmap[.AvailabilityZoneId].AZName // "N/A"), .Score]
    | @tsv
  ' "$spot_file" "$az_file"
} | column -t

rm -f "$spot_file" "$az_file"