# Bitbucket IP Whitelisting Automation for AWS Security Group🛡️

This Python script automates the process of fetching the official Bitbucket IP ranges, collapsing them into minimal CIDR blocks, and synchronizing those ranges with a specific **AWS Security Group** ingress rules on port 443 (HTTPS).

It is designed to run periodically (e.g. via a Jenkins job, cron job, or AWS Lambda) to ensure Bitbucket services can always communicate with your AWS infrastructure, especially for services like webhooks as Atlassian occasionally updates its IP feed.

***

## 🚀 Key Features

* **Dynamic Fetching:** Retrieves the latest official IP ranges from the Atlassian IP feed.
* **CIDR Optimization:** Uses the `ipaddress` module to **collapse** contiguous IP ranges into the fewest possible CIDR blocks, conserving AWS Security Group rule quota.
* **Incremental Updates:** Only adds new rules and removes stale rules (**diff-based update**), preserving any existing, unchanged rules.
* **Security Group Rule Limit Check:** Prevents rule addition if the collapsed CIDRs exceed the AWS rule limit (default 60 for AWS VPCs).
* **Dry-Run Mode:** Supports a safe **Dry-Run** option for testing the changes without affecting the AWS Security Group.
* **Slack Notifications:** Sends success or failure alerts to a Slack channel.

***

## ⚙️ Prerequisites

-  **Python 3.x** and the required packages (`requests`, `boto3`).
-  **AWS Credentials:** The execution environment must have valid AWS credentials configured with `ec2:DescribeSecurityGroups`, `ec2:AuthorizeSecurityGroupIngress`, and `ec2:RevokeSecurityGroupIngress` permissions.
-  **Slack Bot Token:** A Slack Bot Token with permissions to post messages to the target channel.

***

## 📝 Environment Variables

The script relies on several environment variables for configuration:

| Variable | Description | Required | Example |
| :--- | :--- | :--- | :--- |
| `AWS_SG_ID` | The ID of the AWS Security Group to update. | Yes | `sg-0a1b2c3d4e5f6g7h8` |
| `AWS_REGION` | The AWS region where the Security Group resides. | Yes | `us-east-1` |
| `SLACK_BOT_TOKEN` | Slack Bot Token for sending notifications. | Yes | `xoxb-12345...` |
| `DRY_RUN` | If set to `true`, the script performs all checks but *skips* the final AWS update. | No | `true` or `false` |
| `JENKINS_URL` | Contextual URL for the Jenkins job (for Slack alerts). | No | `https://jenkins.mycompany.com` |
| `JOB_NAME` | Contextual name of the Jenkins job (for Slack alerts). | No | `bitbucket-ip-sync` |

***

## 📦 Installation and Usage

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Set the necessary environment variables (e.g., in your shell or CI/CD system).
```bash
export AWS_SG_ID="sg-xxxxxxxxxxxxxxxxx"
export AWS_REGION="us-west-2"
export SLACK_BOT_TOKEN="xoxb-..."
# export DRY_RUN="true" # Optional, for testing
```

### 3. Run the Script
Execute the Python script:
```bash
python bitbucket-aws-sg-whitelister.py
```

### Example Output
```bash
🔍 Fetching Bitbucket 'egress' IPs from [https://ip-ranges.atlassian.com/](https://ip-ranges.atlassian.com/) ...

🔹 Total CIDRs (before collapse): 18
✅ Total CIDRs (after collapse): 10
📉 Reduced by 8 CIDRs (44.4%)

📋 Bitbucket IPv4 egress IP ranges: 10
  104.192.140.0/22
  107.23.23.0/24
  ...

🔑 Current SG (sg-xxxxxxxxxxxxxxxxx) CIDRs: 8
  104.192.140.0/22
  ...
  203.0.113.0/24

⚡ Checking Security Group for differences...

🗑  Removing below 1 stale rules...
  203.0.113.0/24

➕ Adding below 3 new rules...
  1.2.3.4/32
  5.6.7.8/32
  9.10.11.12/32

✅ Updated Security Group with 10 Bitbucket IP CIDRs.

📤 Slack alert sent to #alerts
```

## ⚠️ Notes
* **Target Port:** The script manages Ingress rules for TCP Port 443 (HTTPS). If you need to manage other ports, you must modify the variable "AWS_SG_RULE_PORT".

* **Rule Descriptions:** All rules added by this script are tagged with the description: "Bitbucket CIDR rule added via automation".

## ⚖️ License
This project is licensed under the [MIT License](LICENSE) - see the file for details.
