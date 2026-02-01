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
import subprocess
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


def parse_comma_separated(arg_list):
    """Parse a list of potentially comma-separated values into a flat list.

    Args:
        arg_list: List of strings, each potentially containing comma-separated values

    Returns:
        List of individual values (always returns a list, empty if no values)
    """
    result = []
    for val in arg_list:
        for part in val.split(','):
            part = part.strip()
            if part:
                result.append(part)
    return result


def find_issues(labels=[], exclude_labels=[], issues=[], exclude_issues=[]):
    """Return a list of issue numbers that match the filtering criteria.

    Parameters (all optional keyword arguments with empty list defaults):
        labels (list[str]): Only include issues with ALL of these labels (AND logic). Default: []
        exclude_labels (list[str]): Exclude issues with ANY of these labels (OR logic). Default: []
        issues (list[int]): Only include these specific issue numbers. Default: []
        exclude_issues (list[int]): Exclude these specific issue numbers. Default: []

    Returns:
        list[int]: Sorted list of issue numbers matching all criteria
    """
    # Get all issue numbers from directory
    all_numbers = get_issue_numbers()

    # Apply issue number filters
    if issues:
        # Filter to only requested issues
        numbers = [n for n in all_numbers if n in issues]
        # Log warning for requested issues not in directory
        missing = set(issues) - set(all_numbers)
        for num in sorted(missing):
            logger.warning(f"issue {num} not found in issues directory")
    else:
        numbers = all_numbers

    # Remove excluded issues
    numbers = [n for n in numbers if n not in exclude_issues]

    # Apply label filters
    result = []
    for num in numbers:
        try:
            issue = load_issue(num)
        except FileNotFoundError:
            logger.warning(f"issue {num}: file not found")
            continue

        issue_labels = get_issue_labels(issue)

        # Check label filters
        if labels:
            # Must have ALL labels (AND logic)
            if not all(l in issue_labels for l in labels):
                continue

        # Skip if has ANY excluded label (OR logic)
        if any(l in issue_labels for l in exclude_labels):
            continue

        result.append(num)

    return sorted(result)


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
    stream.write("#:\n")
    stream.write(f"#: https://github.com/en-wl/wordlist/issues/{issue_number}\n")
    stream.write("#:\n")

    # Write each section and block
    for section, block in extraction_results:
        stream.write("\n\n")
        stream.write(f"#: {section}\n\n")
        stream.write(block + "\n\n")

    # Write final blank line
    stream.write("\n")


def main_init():
    # Configure logging
    logging.basicConfig(
        level=logging.WARNING,
        format='%(message)s',
        stream=sys.stderr
    )

    parser = argparse.ArgumentParser(
        description='Extract SCOWL entries from GitHub issue comments.')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Common arguments for all subcommands
    def add_common_args(subparser):
        subparser.add_argument('--section', default='all',
                               choices=['extra', 'signature', 'other', 'all'],
                               help='Which code-block sections to include (default: all)')
        subparser.add_argument('--label', '--labels', dest='labels', action='append', default=[],
                               help='Only include issues with this label (repeatable, comma-separated)')
        subparser.add_argument('--exclude-labels', action='append', default=[],
                               help='Exclude issues with this label (repeatable, comma-separated)')
        subparser.add_argument('--issue', '--issues', dest='issues', action='append', default=[],
                               help='Limit to specific issue numbers (comma-separated, repeatable)')
        subparser.add_argument('--exclude-issues', dest='exclude_issues', action='append', default=[],
                               help='Exclude specific issue numbers (comma-separated, repeatable)')
        subparser.add_argument('--verbose', '-v', action='store_true',
                               help='Enable verbose logging (INFO level)')

    # dump subcommand
    dump_parser = subparsers.add_parser('dump', help='Extract and output SCOWL entries (default)')
    add_common_args(dump_parser)

    # import subcommand
    import_parser = subparsers.add_parser('import', help='Import entries into database')
    add_common_args(import_parser)
    import_parser.add_argument('--db', default='llm.db',
                               help='Path to SQLite database file (default: llm.db)')
    import_parser.add_argument('--use-tags', action='store_true', default=False,
                               help='Tag each merge with issue number and section')

    args = parser.parse_args()

    # Require a command
    if not args.command:
        parser.error('Please specify a command: dump, import')

    # Handle verbose flag
    if args.verbose:
        logging.getLogger().setLevel(logging.INFO)

    # Parse all arguments with comma-separation support
    label_filter = parse_comma_separated(args.labels)
    exclude_label_filter = parse_comma_separated(args.exclude_labels)
    issue_filter = parse_comma_separated(args.issues)
    exclude_issue_filter = parse_comma_separated(args.exclude_issues)

    # Convert issue numbers to integers
    issue_filter = [int(x) for x in issue_filter]
    exclude_issue_filter = [int(x) for x in exclude_issue_filter]

    # Merge SKIP_ISSUES into exclude_issues
    exclude_issue_filter.extend(SKIP_ISSUES)

    # Find matching issues (handles missing files internally with logging)
    numbers = find_issues(
        labels=label_filter,
        exclude_labels=exclude_label_filter,
        issues=issue_filter,
        exclude_issues=exclude_issue_filter
    )

    output_blocks = {}
    tally = {}

    # Extract issues
    for num in numbers:
        results = extract_issue(num, args.section, tally)
        if results:
            output_blocks[num] = results

    # Summary
    logger.info("\n--- summary ---")
    logger.info(f"extracted: {tally.get('processed', 0)}")
    if tally.get('no_comments', 0):
        logger.info(f"skipped (no comments): {tally['no_comments']}")
    if tally.get('no_scowl', 0):
        logger.info(f"skipped (no SCOWL comment): {tally['no_scowl']}")
    if tally.get('no_codeblock', 0):
        logger.info(f"skipped (no code blocks): {tally['no_codeblock']}")

    return args.command, args, output_blocks

if __name__ == '__main__':
    cmd, args, output_blocks = main_init()

    if cmd == 'dump':
        for num in sorted(output_blocks.keys()):
            format_issue(num, output_blocks[num])
        exit(0)

    # Import command
    had_errors = False

    for num, extraction_results in output_blocks.items():
        for section, block in extraction_results:
            if section == 'signature':
                section = 'sig'

            scowl_cmd = ['scowl/scowl', '--db', args.db, 'merge']
            proc = subprocess.Popen(scowl_cmd, stdin=subprocess.PIPE, text=True)
            pipe = proc.stdin

            if args.use_tags:
                pipe.write(f"#:: merge [{num}-{section}]\n\n")
            else:
                pipe.write("#:: merge\n\n")
                
            pipe.write(block)
            pipe.write("\n")
            
            pipe.close()

            ret = proc.wait()
            if ret != 0:
                logger.error(f"scowl merge failed for issue {num} section {section} (exit code {ret})")
                had_errors = True

    if had_errors:
        logger.error("Import completed with errors")
        exit(1)

    exit(0)

        
          
        
