#!/usr/bin/env python3

import requests
import json
import os

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

# Print results
print(f"Found {len(all_issues)} open issues with label 'too add'\n")
for issue in all_issues:
    print(f"#{issue['number']}: {issue['title']}")
    print(f"  Labels: {[label['name'] for label in issue['labels']]}")
    print(f"  Comments: {issue['comments']}")
    print()
