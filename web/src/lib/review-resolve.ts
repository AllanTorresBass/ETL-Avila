import { createHash } from "node:crypto";
import { sql } from "@/lib/db";

type Db = ReturnType<typeof sql>;
type Query = ReturnType<Db>;

/** Same as Python `provenance.value_hash`, so hashes from both writers compare. */
function valueHash(value: string): string {
  const text = value.split(/\s+/).filter(Boolean).join(" ").toLowerCase();
  return createHash("sha256").update(text, "utf8").digest("hex").slice(0, 16);
}

function prov(
  db: Db,
  entity: string,
  entityId: string,
  field: string,
  newValue: string,
  ruleId: string,
  reviewer: string,
  reviewId: string,
): Query {
  return db`
    INSERT INTO avila.field_provenance (
      entity, entity_id, field, old_value_hash, new_value_hash,
      source_kind, source_ref, rule_id, reason
    ) VALUES (
      ${entity}, ${entityId}, ${field}, NULL, ${valueHash(newValue)},
      'review', ${`review_item:${reviewId}`}, ${ruleId}, ${`resolved by ${reviewer}`}
    )
  `;
}

type PersonRow = {
  identity_type: string;
  identity_number: string | null;
  full_name: string | null;
  birth_date: string | null;
  phone: string | null;
  address: string | null;
};

function mergeQueries(
  db: Db,
  survivor: string,
  alias: string,
  aliasRow: PersonRow,
  reviewer: string,
  reviewId: string,
): Query[] {
  return [
    db`
      UPDATE avila.invoice_person s
      SET role = a.role, parentesco = coalesce(s.parentesco, a.parentesco), source = a.source
      FROM avila.invoice_person a
      WHERE a.person_id = ${alias}::uuid AND s.person_id = ${survivor}::uuid
        AND s.invoice_id = a.invoice_id AND s.role = 'unknown' AND a.role <> 'unknown'
    `,
    db`
      UPDATE avila.invoice_person SET person_id = ${survivor}::uuid
      WHERE person_id = ${alias}::uuid AND NOT EXISTS (
        SELECT 1 FROM avila.invoice_person x
        WHERE x.invoice_id = avila.invoice_person.invoice_id AND x.person_id = ${survivor}::uuid)
    `,
    db`DELETE FROM avila.invoice_person WHERE person_id = ${alias}::uuid`,
    db`UPDATE avila.document SET person_id = ${survivor}::uuid WHERE person_id = ${alias}::uuid`,
    db`UPDATE avila.authorization_line SET person_id = ${survivor}::uuid WHERE person_id = ${alias}::uuid`,
    db`UPDATE avila.review_item SET person_id = ${survivor}::uuid WHERE person_id = ${alias}::uuid`,
    db`UPDATE avila.review_item SET other_person_id = ${survivor}::uuid WHERE other_person_id = ${alias}::uuid`,
    // The unique (identity_type, identity_number) must be free before the survivor takes the CI.
    db`DELETE FROM avila.person WHERE id = ${alias}::uuid`,
    db`
      UPDATE avila.person SET
        full_name = coalesce(nullif(full_name, ''), ${aliasRow.full_name}),
        birth_date = coalesce(birth_date, ${aliasRow.birth_date}::date),
        phone = coalesce(nullif(phone, ''), ${aliasRow.phone}),
        address = coalesce(nullif(address, ''), ${aliasRow.address}),
        identity_type = CASE WHEN identity_number IS NULL AND ${aliasRow.identity_number}::text IS NOT NULL
                             THEN ${aliasRow.identity_type}::avila.identity_type ELSE identity_type END,
        identity_number = coalesce(identity_number, ${aliasRow.identity_number}),
        updated_at = now()
      WHERE id = ${survivor}::uuid
    `,
    prov(db, "person", survivor, "merged_from", alias, "review_merge_person", reviewer, reviewId),
  ];
}

function promoteQueries(
  db: Db,
  invoiceId: string,
  personId: string,
  reviewer: string,
  reviewId: string,
): Query[] {
  return [
    db`
      UPDATE avila.invoice_person SET role = 'beneficiario', source = 'review'
      WHERE invoice_id = ${invoiceId}::uuid AND role = 'titular' AND person_id <> ${personId}::uuid
    `,
    db`
      INSERT INTO avila.invoice_person (invoice_id, person_id, role, source)
      VALUES (${invoiceId}::uuid, ${personId}::uuid, 'titular', 'review')
      ON CONFLICT (invoice_id, person_id) DO UPDATE SET role = 'titular', source = 'review'
    `,
    prov(
      db, "invoice_person", `${invoiceId}:${personId}`, "role", "titular",
      "review_promote_titular", reviewer, reviewId,
    ),
  ];
}

function mergeMedicoQueries(
  db: Db,
  survivor: string,
  alias: string,
  reviewer: string,
  reviewId: string,
): Query[] {
  return [
    db`
      INSERT INTO avila.medico_especialidad (medico_id, especialidad_id, source, evidence_count, is_primary)
      SELECT ${survivor}::uuid, especialidad_id, source, evidence_count, false
      FROM avila.medico_especialidad WHERE medico_id = ${alias}::uuid
      ON CONFLICT (medico_id, especialidad_id) DO UPDATE SET
        evidence_count = avila.medico_especialidad.evidence_count + EXCLUDED.evidence_count,
        updated_at = now()
    `,
    db`UPDATE avila.atencion SET medico_id = ${survivor}::uuid, updated_at = now() WHERE medico_id = ${alias}::uuid`,
    db`UPDATE avila.medico_mention SET medico_id = ${survivor}::uuid WHERE medico_id = ${alias}::uuid`,
    db`UPDATE avila.medico SET merged_into = ${survivor}::uuid, updated_at = now() WHERE id = ${alias}::uuid`,
    db`UPDATE avila.medico SET merged_into = ${survivor}::uuid, updated_at = now() WHERE merged_into = ${alias}::uuid`,
    prov(db, "medico", survivor, "merged_from", alias, "review_merge_medico", reviewer, reviewId),
    prov(db, "medico", alias, "merged_into", survivor, "review_merge_medico", reviewer, reviewId),
  ];
}

function linkAtencionPersonQueries(
  db: Db,
  atencionId: string,
  personId: string,
  reviewer: string,
  reviewId: string,
): Query[] {
  return [
    db`
      UPDATE avila.atencion SET
        person_id = ${personId}::uuid,
        person_link_rule = 'review',
        link_status = CASE
          WHEN medico_id IS NOT NULL AND especialidad_id IS NOT NULL THEN 'complete'
          ELSE 'partial'
        END,
        updated_at = now()
      WHERE id = ${atencionId}::uuid
    `,
    prov(db, "atencion", atencionId, "person_id", personId, "review_atencion_patient", reviewer, reviewId),
  ];
}

export async function resolveReviewDecision(
  reviewer: string,
  id: string,
  decision: "accept" | "reject",
): Promise<"missing" | "done"> {
  const db = sql();
  const [item] = await db`
    SELECT id, kind, status, person_id, other_person_id, invoice_id, authorization_line_id,
           medico_id, other_medico_id, atencion_id
    FROM avila.review_item WHERE id = ${id}::uuid
  `;
  if (!item || item.status !== "open") return "missing";

  const close = db`
    UPDATE avila.review_item
    SET status = ${decision === "accept" ? "accepted" : "rejected"},
        resolved_by = ${reviewer}, resolved_at = now(), updated_at = now()
    WHERE id = ${id}::uuid AND status = 'open'
  `;
  const effects: Query[] = [];
  if (decision === "accept") {
    if (item.kind === "duplicate_candidate" && item.person_id && item.other_person_id) {
      const [survivorRow] = await db`
        SELECT identity_number FROM avila.person WHERE id = ${item.person_id}::uuid
      `;
      const [aliasRow] = await db`
        SELECT identity_type::text AS identity_type, identity_number, full_name,
               birth_date::text AS birth_date, phone, address
        FROM avila.person WHERE id = ${item.other_person_id}::uuid
      `;
      if (!survivorRow || !aliasRow) {
        throw new Error("PERSON_MISSING");
      }
      if (
        survivorRow.identity_number &&
        aliasRow.identity_number &&
        survivorRow.identity_number !== aliasRow.identity_number
      ) {
        throw new Error("CI_CONFLICT");
      }
      effects.push(
        ...mergeQueries(db, item.person_id, item.other_person_id, aliasRow as PersonRow, reviewer, id),
      );
    } else if (
      (item.kind === "ci_conflict" || item.kind === "workbook_titular") &&
      item.invoice_id &&
      item.person_id
    ) {
      effects.push(...promoteQueries(db, item.invoice_id, item.person_id, reviewer, id));
    } else if (item.kind === "auth_match" && item.authorization_line_id && item.invoice_id) {
      const personId = item.person_id;
      effects.push(
        db`
          UPDATE avila.authorization_line SET invoice_id = ${item.invoice_id}::uuid, updated_at = now()
          WHERE id = ${item.authorization_line_id}::uuid
        `,
        prov(
          db, "authorization_line", item.authorization_line_id, "invoice_id", item.invoice_id,
          "review_auth_match", reviewer, id,
        ),
      );
      // Mirror auto-link: attach the auth person as beneficiario when missing.
      if (personId) {
        effects.push(
          db`
            INSERT INTO avila.invoice_person (invoice_id, person_id, role, source)
            VALUES (${item.invoice_id}::uuid, ${personId}::uuid, 'beneficiario', 'auth_match')
            ON CONFLICT (invoice_id, person_id) DO UPDATE SET
              role = CASE
                WHEN avila.invoice_person.role = 'titular' THEN avila.invoice_person.role
                WHEN avila.invoice_person.role = 'unknown' THEN 'beneficiario'
                ELSE avila.invoice_person.role
              END,
              source = CASE
                WHEN avila.invoice_person.source = 'legacy_unknown' THEN 'auth_match'
                ELSE avila.invoice_person.source
              END
          `,
          prov(
            db, "invoice_person", `${item.invoice_id}:${personId}`, "role", "beneficiario",
            "review_auth_match_beneficiario", reviewer, id,
          ),
        );
      }
    } else if (item.kind === "medico_duplicate" && item.medico_id && item.other_medico_id) {
      if (item.medico_id === item.other_medico_id) throw new Error("SAME_MEDICO");
      effects.push(...mergeMedicoQueries(db, item.medico_id, item.other_medico_id, reviewer, id));
    } else if (item.kind === "atencion_patient") {
      if (!item.atencion_id || !item.person_id) throw new Error("NO_CANDIDATE");
      effects.push(...linkAtencionPersonQueries(db, item.atencion_id, item.person_id, reviewer, id));
    }
  }
  await db.transaction([close, ...effects]);
  return "done";
}
