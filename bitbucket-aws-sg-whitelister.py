"""
Automation to whitelist Bitbucket IPs in AWS security group.
"""

import ipaddress
import os
import sys
import requests
import boto3

# Constants
IP_FEED_URL = "https://ip-ranges.atlassian.com/"  # Bitbucket IP feed
AWS_SG_RULE_LIMIT = 60
AWS_SG_RULE_PORT = 443
RULE_DESCRIPTION = "Bitbucket CIDR rule added via automation"

AWS_SG_ID = os.getenv("AWS_SG_ID")
AWS_REGION = os.getenv("AWS_REGION")
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
JENKINS_URL = os.getenv("JENKINS_URL")
JOB_NAME = os.getenv("JOB_NAME")

# Slack config
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL = "#devops-jenkins"


def fetch_ip_ranges():
    """
    Fetch data from Bitbucket feed.
    """
    resp = requests.get(IP_FEED_URL, timeout=10)
    resp.raise_for_status()
    return resp.json()


def extract_bitbucket_egress_ipv4(data):
    """
    Filter and extract Bitbucket CIDRs from feed data.
    """
    cidrs = [
        item["cidr"]
        for item in data.get("items", [])
        if "bitbucket" in item.get("product", [])
        and "egress" in item.get("direction", [])
        and ":" not in item.get("cidr", "")  # exclude IPv6
    ]

    cidr_objs = [ipaddress.ip_network(c) for c in cidrs]
    collapsed = list(ipaddress.collapse_addresses(cidr_objs))
    return cidrs, [str(c) for c in sorted(collapsed, key=lambda c: (c.network_address, c.prefixlen))]


def get_sg_ingress_rules():
    """
    Get current ingress rules (port 443) from AWS security group.
    """
    ec2 = boto3.client("ec2", region_name=AWS_REGION)
    ec2_sg = ec2.describe_security_groups(GroupIds=[AWS_SG_ID])["SecurityGroups"][0]
    rules = []
    for perm in ec2_sg.get("IpPermissions", []):
        if perm.get("IpProtocol") == "tcp" and perm.get("FromPort") == AWS_SG_RULE_PORT:
            rules.extend([ip["CidrIp"] for ip in perm.get("IpRanges", [])])
    return sorted(rules, key=ipaddress.ip_network)


def replace_sg_ingress_rules(after_cidrs, current_cidrs):
    """
    Update AWS security group rules incrementally:
    - Add only missing CIDRs
    - Remove only stale CIDRs
    - Preserve unchanged rules
    """
    ec2 = boto3.client("ec2", region_name=AWS_REGION)
    print("\n⚡ Checking Security Group for differences...")
    current = set(current_cidrs)
    desired = set(after_cidrs)

    to_add = desired - current
    to_remove = current - desired

    if not to_add and not to_remove:
        print("✅ SG already up-to-date. No changes required.")
        return

    if to_remove:
        print(f"\n🗑  Removing below {len(to_remove)} stale rules...")
        for cidr in to_remove:
            print(f"  {cidr}")
        if not DRY_RUN:
            revoke_payload = [{
                "IpProtocol": "tcp",
                "FromPort": AWS_SG_RULE_PORT,
                "ToPort": AWS_SG_RULE_PORT,
                "IpRanges": [{"CidrIp": c} for c in to_remove]
            }]
            ec2.revoke_security_group_ingress(
                GroupId=AWS_SG_ID, IpPermissions=revoke_payload)

    if to_add:
        print(f"\n➕ Adding below {len(to_add)} new rules...")
        for cidr in to_add:
            print(f"  {cidr}")
        if not DRY_RUN:
            auth_payload = [{
                "IpProtocol": "tcp",
                "FromPort": AWS_SG_RULE_PORT,
                "ToPort": AWS_SG_RULE_PORT,
                "IpRanges": [{"CidrIp": c, "Description": RULE_DESCRIPTION} for c in to_add]
            }]
            ec2.authorize_security_group_ingress(
                GroupId=AWS_SG_ID, IpPermissions=auth_payload)

    if DRY_RUN:
        print("\n🟡 DRY-RUN mode: Not updating SG in AWS.")
        sys.exit()


def send_slack_alert(message: str):
    """
    Send Slack notifications using bot token.
    """
    if not SLACK_BOT_TOKEN:
        print("⚠️ SLACK_BOT_TOKEN not set, exiting..")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "channel": SLACK_CHANNEL,
        "text": message,
        "mrkdwn": True
    }

    try:
        resp = requests.post("https://slack.com/api/chat.postMessage",
                             headers=headers, json=payload, timeout=10)
        data = resp.json()
        if not data.get("ok"):
            raise Exception(data)
        print(f"\n📤 Slack alert sent to {SLACK_CHANNEL}")
    except Exception as e:
        print(f"❌ Failed to send Slack alert: {e}")


def main():
    print(f"🔍 Fetching Bitbucket 'egress' IPs from {IP_FEED_URL} ...\n")
    data = fetch_ip_ranges()
    before_cidrs, after_cidrs = extract_bitbucket_egress_ipv4(data)

    before_count = len(before_cidrs)
    after_count = len(after_cidrs)
    print(f"🔹 Total CIDRs (before collapse): {before_count}")
    print(f"✅ Total CIDRs (after collapse): {after_count}")

    if before_count > after_count:
        reduction = ((before_count - after_count) / before_count) * 100
        print(f"📉 Reduced by {before_count - after_count} CIDRs ({reduction:.1f}%)")
    else:
        print("ℹ️ No reduction after collapsing CIDRs")

    print(f"\n📋 Bitbucket IPv4 egress IP ranges: {len(after_cidrs)}")
    for cidr in after_cidrs:
        print(f"  {cidr}")

    # Fetch SG rules
    current_cidrs = get_sg_ingress_rules()
    print(f"\n🔑 Current SG ({AWS_SG_ID}) CIDRs: {len(current_cidrs)}")
    for cidr in current_cidrs:
        print(f"  {cidr}")

    if after_cidrs == current_cidrs:
        print("\n✅ No changes detected in SG rules.")
        return

    # Check SG rule limit
    if len(after_cidrs) > AWS_SG_RULE_LIMIT:
        alert_msg = (
            f"🚨 ALERT: NOT able to update Security group !!\n"
            f"Bitbucket IP CIDRs = {len(after_cidrs)}, exceeds AWS SG limit of {AWS_SG_RULE_LIMIT}.\n"
            f"*Jenkins SG:* `{AWS_SG_ID}`\n"
            f"*Jenkins URL:* `{JENKINS_URL}`\n"
            f"*Jenkins Job:* `{JOB_NAME}`"
        )
        print("\n🚨 ALERT: NOT able to update Security group !!")
        print(f"Bitbucket IP CIDRs = {len(after_cidrs)}, exceeds AWS SG limit of {AWS_SG_RULE_LIMIT}.")
        if not DRY_RUN:
            send_slack_alert(alert_msg)
        sys.exit(1)

    # Update SG with diffs
    replace_sg_ingress_rules(after_cidrs, current_cidrs)

    success_msg = (
        f"✅ Updated Security Group with {len(after_cidrs)} Bitbucket IP CIDRs.\n"
        f"*Jenkins SG:* `{AWS_SG_ID}`\n"
        f"*Jenkins URL:* `{JENKINS_URL}`\n"
        f"*Jenkins Job:* `{JOB_NAME}`"
    )
    print(f"\n✅ Updated Security Group with {len(after_cidrs)} Bitbucket IP CIDRs.")
    send_slack_alert(success_msg)


if __name__ == "__main__":
    main()
