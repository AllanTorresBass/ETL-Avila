-- Collation-independent folded name (matches person_upsert.fold_person_name for
-- Spanish text). Postgres lower() under the C collation does not fold Ñ / accents.

-- Decomposed input (n + U+0303) is handled by stripping combining marks first.
ALTER TABLE avila.person DROP COLUMN IF EXISTS name_folded;
ALTER TABLE avila.person
  ADD COLUMN name_folded text GENERATED ALWAYS AS (
    btrim(regexp_replace(
      lower(translate(
        regexp_replace(coalesce(full_name, ''), '[\u0300-\u036f]', '', 'g'),
        'ÁÀÄÂÉÈËÊÍÌÏÎÓÒÖÔÚÙÜÛÑÇáàäâéèëêíìïîóòöôúùüûñç',
        'AAAAEEEEIIIIOOOOUUUUNCaaaaeeeeiiiioooouuuunc'
      )),
      '\s+', ' ', 'g'
    ))
  ) STORED;

CREATE INDEX IF NOT EXISTS idx_avila_person_name_folded ON avila.person (name_folded);
