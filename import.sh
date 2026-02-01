#!/bin/sh

set -e

rm -f llm.db

scowl/scowl --db=llm.db init-db

./extract.py import --db=llm.db --use-tags

sqlite3 llm.db <<EOF
.mode tabs
.once 'input.tsv'
with
  q as (select distinct group_id as gid,word,base_pos
          from scowl_
        where size <= 60 and word_id = lemma_id and base_pos in ('n','v','aj','av'))
select gid, string_agg(word,', ') as lemmas, base_pos from q group by gid, base_pos
EOF
