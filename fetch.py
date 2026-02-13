#!/usr/bin/env python3

import requests
import json
import os
import shutil

# Read token from file
with open("github-token.txt", "r") as f:
    token = f.read().strip()

headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json"
}

# Fetch all open issues with label "too add" with pagination
url = "https://api.github.com/repos/en-wl/wordlist/issues"
params = {
    "labels": "to add",
    "state": "open",
    "per_page": 100  # Max results per page
}

# Capture existing issue numbers before fetching
existing_issues = set()
if os.path.exists("issues"):
    for filename in os.listdir("issues"):
        # Match pattern: {number}.json (not -comments.json)
        if filename.endswith('.json') and not filename.endswith('-comments.json'):
            issue_num = filename[:-5]  # Remove .json extension
            if issue_num.isdigit():
                existing_issues.add(int(issue_num))

page = 1
all_issues = []

while True:
    params["page"] = page
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()

    issues = response.json()
    if not issues:  # No more issues
        break

    all_issues.extend(issues)
    page += 1

# Create issues directory if it doesn't exist
os.makedirs("issues", exist_ok=True)

# Save each issue and its comments
for issue in all_issues:
    # Save issue metadata
    filename = f"issues/{issue['number']}.json"
    with open(filename, "w") as f:
        json.dump(issue, f, indent=2)

    # Fetch and save comments
    if issue['comments'] > 0:
        comments_url = f"https://api.github.com/repos/en-wl/wordlist/issues/{issue['number']}/comments"
        comments_response = requests.get(comments_url, headers=headers, params={"per_page": 100})
        comments_response.raise_for_status()
        comments = comments_response.json()

        comments_filename = f"issues/{issue['number']}-comments.json"
        with open(comments_filename, "w") as f:
            json.dump(comments, f, indent=2)

# Create issues-old directory if it doesn't exist
os.makedirs("issues-old", exist_ok=True)

# Build set of fetched issue numbers
fetched_issues = set(issue['number'] for issue in all_issues)

# Identify stale issues (existed before but not fetched now)
stale_issues = existing_issues - fetched_issues

# Move stale issues to issues-old
archived_count = 0
for issue_num in sorted(stale_issues):
    # Move base issue file
    base_file = f"issues/{issue_num}.json"
    if os.path.exists(base_file):
        shutil.move(base_file, f"issues-old/{issue_num}.json")
        archived_count += 1

    # Move comments file if it exists
    comments_file = f"issues/{issue_num}-comments.json"
    if os.path.exists(comments_file):
        shutil.move(comments_file, f"issues-old/{issue_num}-comments.json")

# Print results
print(f"Found {len(all_issues)} open issues with label 'to add'")
if archived_count > 0:
    print(f"Archived {archived_count} stale issue(s) to issues-old/")
    if stale_issues:
        print(f"  Archived issues: {', '.join(f'#{num}' for num in sorted(stale_issues))}")
print()

# for issue in all_issues:
#     print(f"#{issue['number']}: {issue['title']}")
#     print(f"  Labels: {[label['name'] for label in issue['labels']]}")
#     print(f"  Comments: {issue['comments']}")
#     print()
