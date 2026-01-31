#!/usr/bin/env python3

"""Extract SCOWL entries from GitHub issue comments.

Reads issues/*.json and issues/*-comments.json, finds the last comment by
kevina containing SCOWL code blocks, extracts ```text code blocks, and
outputs the SCOWL entries to stdout. Diagnostics go to stderr.
"""

import argparse
import json
import logging
import re
import sys
import os
from collections import defaultdict

logger = logging.getLogger(__name__)

ISSUES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'issues')

SKIP_ISSUES = {265}

# Rough pattern to check if a line looks like a SCOWL entry.
# e.g. "60: deplatform <v>: deplatformed, deplatforming, deplatforms"
SCOWL_LINE_RE = re.compile(r'\d\d.*:.*[A-Za-z].*<[a-z/]+>')

# Match fenced code blocks: ```text or plain ```
CODE_BLOCK_RE = re.compile(r'```(?:text)?\n(.*?)```', re.DOTALL)


def looks_like_scowl(text):
    """Return True if the text contains at least one SCOWL-looking line."""
    for line in text.splitlines():
        if SCOWL_LINE_RE.search(line):
            return True
    return False


def load_issue(number):
    path = os.path.join(ISSUES_DIR, f'{number}.json')
    with open(path) as f:
        return json.load(f)


def load_comments(number):
    path = os.path.join(ISSUES_DIR, f'{number}-comments.json')
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def get_issue_numbers():
    """Return sorted list of issue numbers from the issues directory."""
    numbers = set()
    for name in os.listdir(ISSUES_DIR):
        m = re.match(r'^(\d+)\.json$', name)
        if m:
            numbers.add(int(m.group(1)))
    return sorted(numbers)


def get_issue_labels(issue):
    return [l['name'] for l in issue.get('labels', [])]


def find_scowl_comment(comments):
    """Return the last comment by kevina containing a valid SCOWL code block, or None."""
    found = None
    for comment in comments:
        if comment['user']['login'] != 'kevina':
            continue
        body = comment.get('body', '')
        blocks = CODE_BLOCK_RE.findall(body)
        if any(looks_like_scowl(b) for b in blocks):
            found = comment
    return found


def extract_section_blocks(body, section_filter):
    """Extract ```text code blocks from the comment body, filtered by section.

    section_filter: 'extra', 'signature', 'other', or 'all'

    For 'extra' and 'signature', we look for section headings (### Extra,
    ## SCOWL entries – Extra, ### Signature, etc.) and return code blocks
    that appear under matching headings.

    For 'other', we return code blocks under headings that match neither
    extra nor signature.

    For 'all', we return all ```text code blocks.
    """

    # Split body into sections based on markdown headings (##, ###, etc.)
    # We want to associate each code block with its preceding heading.
    # Be careful not to treat # lines inside fenced code blocks as headings.
    lines = body.split('\n')
    sections = []  # list of (heading_text, content_lines)
    current_heading = ''
    current_lines = []
    in_code_block = False

    for line in lines:
        if line.startswith('```'):
            in_code_block = not in_code_block
            current_lines.append(line)
        elif not in_code_block and re.match(r'^#{1,6}\s+', line):
            if current_lines or current_heading:
                sections.append((current_heading, '\n'.join(current_lines)))
            current_heading = re.sub(r'^#{1,6}\s+', '', line).strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines or current_heading:
        sections.append((current_heading, '\n'.join(current_lines)))

    # Determine which headings match the filter
    results = []
    for heading, content in sections:
        heading_lower = heading.lower()
        is_extra = (('extra' in heading_lower or 'scowl' in heading_lower)
                    and 'signature' not in heading_lower)
        is_signature = 'signature' in heading_lower
        section = 'extra' if is_extra else 'signature' if is_signature else 'other'
        if section_filter == 'all':
            match = True
        else:
            match = section == section_filter
        if match:
            blocks = CODE_BLOCK_RE.findall(content)
            results.append((section, blocks))

    return results


def extract_issue(issue_number, section_filter='all', tally=None):
    """Extract SCOWL code blocks from a single GitHub issue.

    Parameters:
        issue_number (int): GitHub issue number to process
        section_filter (str): One of 'extra', 'signature', 'other', or 'all' (default: 'all')
        tally (dict, optional): Statistics dictionary. If None, creates a new one.

    Returns:
        list[tuple[str, str]]: List of (section, block_text) tuples (flattened format)
                               Returns empty list [] if issue cannot be processed
    """
    if tally is None:
        tally = {}
    tally.setdefault('processed', 0)
    tally.setdefault('no_comments', 0)
    tally.setdefault('no_scowl', 0)
    tally.setdefault('no_codeblock', 0)

    # Load issue - let exceptions propagate
    issue = load_issue(issue_number)

    # Load comments
    comments = load_comments(issue_number)
    if not comments:
        logger.info(f"issue {issue_number}: no comments")
        tally['no_comments'] += 1
        return []

    # Find SCOWL comment
    scowl_comment = find_scowl_comment(comments)
    if scowl_comment is None:
        logger.info(f"issue {issue_number}: no SCOWL comment by kevina")
        tally['no_scowl'] += 1
        return []

    # Extract blocks
    body = scowl_comment['body']
    section_blocks = extract_section_blocks(body, section_filter)
    if not section_blocks:
        logger.info(f"issue {issue_number}: no {section_filter} code blocks found")
        tally['no_codeblock'] += 1
        return []

    # Flatten results: [(section, [blocks]), ...] -> [(section, block), ...]
    flattened = []
    for section, blocks in section_blocks:
        for block in blocks:
            flattened.append((section, block.strip()))

    tally['processed'] += 1
    return flattened


def format_issue(issue_number, extraction_results, stream=None):
    """Format and write extraction results to a stream.

    Parameters:
        issue_number (int): GitHub issue number
        extraction_results (list[tuple[str, str]]): Results from extract_issue()
        stream (file-like, optional): Output stream. Defaults to sys.stdout if None.

    Returns:
        None
    """
    if stream is None:
        stream = sys.stdout

    # Write header
    print("#:", file=stream)
    print(f"#: https://github.com/en-wl/wordlist/issues/{issue_number}", file=stream)
    print("#:", file=stream)
    print(file=stream)

    # Write each section and block
    for section, block in extraction_results:
        print(f"#: {section}", file=stream)
        print(file=stream)
        print(block, file=stream)
        print(file=stream)

    # Write final blank line
    print(file=stream)


def main():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s',
        stream=sys.stderr
    )

    parser = argparse.ArgumentParser(
        description='Extract SCOWL entries from GitHub issue comments.')
    parser.add_argument('--section', default='all',
                        choices=['extra', 'signature', 'other', 'all'],
                        help='Which code-block sections to include (default: all)')
    parser.add_argument('--label', action='append', default=[],
                        help='Only include issues with this label (repeatable)')
    parser.add_argument('--exclude-label', action='append', default=[],
                        help='Exclude issues with this label (repeatable)')
    parser.add_argument('--issue', '--issues', dest='issues', action='append', default=[],
                        help='Limit to specific issue numbers (comma-separated, repeatable)')
    args = parser.parse_args()

    # Parse issue numbers from comma-separated args
    issue_filter = set()
    for val in args.issues:
        for part in val.split(','):
            part = part.strip()
            if part:
                issue_filter.add(int(part))

    all_numbers = get_issue_numbers()
    if issue_filter:
        numbers = [n for n in all_numbers if n in issue_filter]
        missing = issue_filter - set(all_numbers)
        for m in sorted(missing):
            logger.warning(f"issue {m} not found in issues directory")
    else:
        numbers = all_numbers

    output_blocks = {}
    tally = {}
    skipped_label = 0

    for num in numbers:
        if num in SKIP_ISSUES:
            continue

        issue = load_issue(num)
        labels = get_issue_labels(issue)

        # Label filters
        if args.label:
            if not all(l in labels for l in args.label):
                skipped_label += 1
                continue
        if args.exclude_label:
            if any(l in labels for l in args.exclude_label):
                skipped_label += 1
                continue

        # Extract issue
        results = extract_issue(num, args.section, tally)
        if results:
            output_blocks[num] = results

    # Summary
    logger.info("\n--- summary ---")
    logger.info(f"extracted: {tally.get('processed', 0)}")
    if skipped_label:
        logger.info(f"skipped (label filter): {skipped_label}")
    if tally.get('no_comments', 0):
        logger.info(f"skipped (no comments): {tally['no_comments']}")
    if tally.get('no_scowl', 0):
        logger.info(f"skipped (no SCOWL comment): {tally['no_scowl']}")
    if tally.get('no_codeblock', 0):
        logger.info(f"skipped (no code blocks): {tally['no_codeblock']}")

    # Output
    for num in sorted(output_blocks.keys()):
        format_issue(num, output_blocks[num])


if __name__ == '__main__':
    main()
