# Person cleanup report

Mode: **dry-run**

## Before

```json
{
  "persons": 2374,
  "without_ci": 1264,
  "provisional": 1264,
  "duplicate_name_groups": 120,
  "junk_name_left": 128
}
```

## Stats

```json
{
  "junk_candidates": 128,
  "orphan_candidates": 9,
  "provisional_groups": 120,
  "provisional_would_absorb": 818,
  "ci_would_absorb": 2
}
```

## After

```json
{
  "note": "dry-run; after \u2248 before minus candidates",
  "junk_candidates": 128,
  "orphan_candidates": 9,
  "provisional_would_absorb": 818,
  "ci_would_absorb": 2
}
```
