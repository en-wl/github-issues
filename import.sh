#!/bin/sh

set -e

rm -f llm.db

scowl/scowl --db=llm.db init-db

sqlite3 < import-orig.sql

./extract.py import --skip-issues 344  --db=llm.db --use-tags

sqlite3 llm.db <<EOF
.bail on
.mode tabs
.once 'input.tsv'
with
  q as (select distinct group_id as gid,word,base_pos
          from scowl_
        where word_id = lemma_id and base_pos in ('n','v','aj','av','abbr'))
select gid, string_agg(word,', ') as lemmas, base_pos from q group by gid, base_pos;

.once 'github_issues.tsv'
SELECT
    group_id,
    min(size) as size,
    CAST(substr(tag, 2, instr(tag, '-') - 2) AS INTEGER) as issue_num,
    substr(tag, instr(tag, '-') + 1, length(tag) - instr(tag, '-') - 1) as section
FROM scowl_ 
WHERE tag LIKE '[%-%]'
GROUP BY group_id, tag 
ORDER BY group_id, issue_num, section, size;
EOF
