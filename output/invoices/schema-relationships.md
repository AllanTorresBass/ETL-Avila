# Ávila schema relationships

Tables live in the Neon schema `avila` (isolated from other apps sharing the same database).

```mermaid
erDiagram
  Account ||--o{ Invoice : pays
  Person ||--o{ InvoicePerson : appears_on
  Invoice ||--o{ InvoicePerson : lists
  Invoice ||--o{ SourceFile : materialized_as
  SourceFile ||--o{ Document : splits_into
  Person ||--o{ Document : owns
  Invoice ||--o{ Document : belongs_to
  Account {
    uuid id PK
    text code UK
    text legal_name
  }
  Person {
    uuid id PK
    text identity_type
    text identity_number
    text full_name
  }
  Invoice {
    uuid id PK
    text invoice_number UK
    uuid account_id FK
  }
  InvoicePerson {
    uuid invoice_id FK
    uuid person_id FK
    text role
  }
  SourceFile {
    uuid id PK
    uuid invoice_id FK
    text backup_path UK
  }
  Document {
    uuid id PK
    uuid source_file_id FK
    uuid invoice_id FK
    uuid person_id FK
    int page_index
    text document_type
    text blob_pathname
  }
```

## Narrative of one case

1. A packet file such as `FACT 12843.pdf` becomes one `source_file` linked to invoice `12843`.
2. Each rendered page becomes one `document` with its own `document_type` and Blob pathname.
3. If a page is a cédula card, a `person` row is created or matched and linked through `invoice_person`.
4. The billed insurer (for example La Previsora) is the `account` on the invoice, not the client person.
