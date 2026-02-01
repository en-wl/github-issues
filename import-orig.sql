begin;
.bail on

attach 'llm.db' as scowl;

.mode tabs
.import 'input-orig.tsv' orig_input

PRAGMA foreign_keys = ON;

create view orig as
  with recursive split(gid, base_pos, word, rest) as (
    select gid, base_pos,
           trim(substr(lemmas, 1,
                      case when instr(lemmas, ',') > 0
                           then instr(lemmas, ',') - 1
                           else length(lemmas) end)),
           case when instr(lemmas, ',') > 0
                then substr(lemmas, instr(lemmas, ',') + 1)
                else null end
    from orig_input
    union all
    select gid, base_pos,
           trim(substr(rest, 1,
                      case when instr(rest, ',') > 0
                           then instr(rest, ',') - 1
                           else length(rest) end)),
           case when instr(rest, ',') > 0
                then substr(rest, instr(rest, ',') + 1)
                else null end
    from split
    where rest is not null
  )
  select gid, row_number() over (order by gid, word) as word_id, word, base_pos from split;

insert into scowl.groups (group_id, base_pos)
  select distinct gid, base_pos from orig;

insert into scowl.words (group_id, lemma_id, word_id, pos, word)
select gid,word_id,word_id,lemma_pos,word from orig join scowl.base_poses using (base_pos);

select max(group_id) from groups;
select max(word_id) from words;

commit;
