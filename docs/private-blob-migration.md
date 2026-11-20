# Private Blob migration

Private store **`avila-etl-private`** (`store_33dNbTNXfzxujkyI`, region `iad1`, access `private`) was created for project `etl-avila`.

1. Confirm Vercel project env has the store’s `BLOB_READ_WRITE_TOKEN` / `BLOB_STORE_ID` (or copy them from the Blob store dashboard into repo-root `.env`).
2. Set `BLOB_ACCESS=private`.
3. Re-run the loader so pages are written privately:

```bash
export BLOB_ACCESS=private
python3 scripts/upload_documents_to_blob.py
```

5. Confirm the reader preview still uses `/api/blob/[documentId]` (authenticated). Legacy public `blob_url` rows keep working via the fetch fallback until re-uploaded.
6. For local uploads, pull the new `BLOB_READ_WRITE_TOKEN` from the Vercel project env (Dashboard → etl-avila → Settings → Environment Variables) into repo-root `.env`. Do not commit it.
7. Apply `sql/007_app_access.sql` and seed staff with `scripts/seed_app_users.mjs` before deploying the reader.
