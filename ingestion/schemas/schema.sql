-- Normalized schema for eSAKSHI public-portal data (Phase 4 / Phase 12).
--
-- PostgreSQL. The existing mplads-intel pipeline is parquet-based and this
-- module does NOT replace it: these tables are the ingestion module's own
-- store, and `ingestion/normalizer/normalize.py` writes the same shapes as
-- parquet so the two can coexist. Load this only if a database is wanted.
--
-- Two design points worth stating rather than discovering later:
--
--  * The work key is (work_recommendation_dtl_id, mp_id), not work_id. The
--    portal's own `WORK_ID` is issued at completion and is absent on every open
--    work. It is preserved as `portal_work_id` for traceability and never
--    joined on. This matches docs/DATA_CONTRACT.md.
--
--  * There is no district table populated from works. The portal exposes no
--    district dimension for a work; `ida_name` is a district *office* string.
--    The table exists because the citizen-recommendation controller has a
--    district endpoint, but it is left empty by this pipeline rather than
--    filled with a guess.

BEGIN;

CREATE TABLE IF NOT EXISTS sources (
    source_id       BIGSERIAL PRIMARY KEY,
    source_url      TEXT        NOT NULL,
    http_method     TEXT        NOT NULL,
    request_body    TEXT,
    http_status     INTEGER     NOT NULL,
    content_type    TEXT,
    file_size       BIGINT      NOT NULL,
    sha256          CHAR(64)    NOT NULL,
    stored_path     TEXT        NOT NULL,
    artefact_kind   TEXT        NOT NULL,
    retrieved_at    TIMESTAMPTZ NOT NULL,
    note            TEXT,
    UNIQUE (stored_path, sha256, retrieved_at)
);
CREATE INDEX IF NOT EXISTS sources_sha_idx ON sources (sha256);

CREATE TABLE IF NOT EXISTS states (
    state_id   INTEGER PRIMARY KEY,
    state_name TEXT NOT NULL,
    source_id  BIGINT REFERENCES sources (source_id)
);

CREATE TABLE IF NOT EXISTS districts (
    district_id   BIGSERIAL PRIMARY KEY,
    state_id      INTEGER REFERENCES states (state_id),
    district_name TEXT NOT NULL,
    source_id     BIGINT REFERENCES sources (source_id),
    UNIQUE (state_id, district_name)
);

CREATE TABLE IF NOT EXISTS constituencies (
    constituency_id   INTEGER PRIMARY KEY,
    state_id          INTEGER NOT NULL REFERENCES states (state_id),
    constituency_name TEXT    NOT NULL,
    source_id         BIGINT  REFERENCES sources (source_id)
);

CREATE TABLE IF NOT EXISTS tenures (
    tenure_id  INTEGER PRIMARY KEY,
    house      SMALLINT NOT NULL,   -- 2 = Lok Sabha, 1 = Rajya Sabha
    caption    TEXT     NOT NULL,
    source_id  BIGINT   REFERENCES sources (source_id)
);

CREATE TABLE IF NOT EXISTS mps (
    mp_id            INTEGER PRIMARY KEY,
    mp_name          TEXT     NOT NULL,
    house            SMALLINT NOT NULL,
    state_id         INTEGER  REFERENCES states (state_id),
    constituency_id  INTEGER  REFERENCES constituencies (constituency_id),
    tenure_id        INTEGER  REFERENCES tenures (tenure_id),
    allocated_amount NUMERIC(18, 2),
    tenure_start     TIMESTAMPTZ,
    tenure_end       TIMESTAMPTZ,
    source_id        BIGINT   REFERENCES sources (source_id)
);

CREATE TABLE IF NOT EXISTS agencies (
    agency_id   BIGSERIAL PRIMARY KEY,
    agency_name TEXT NOT NULL,
    agency_role TEXT NOT NULL,   -- 'IDA' (district authority) or 'IA' (implementing agency)
    source_id   BIGINT REFERENCES sources (source_id),
    UNIQUE (agency_name, agency_role)
);

CREATE TABLE IF NOT EXISTS works (
    work_ref                    TEXT PRIMARY KEY,      -- 'MP<mp_id>-W<rec_dtl_id>'
    work_recommendation_dtl_id  BIGINT   NOT NULL,
    mp_id                       INTEGER  NOT NULL REFERENCES mps (mp_id),
    portal_work_id              TEXT,                  -- never join on this
    state_id                    INTEGER  REFERENCES states (state_id),
    constituency_id             INTEGER  REFERENCES constituencies (constituency_id),
    tenure_id                   INTEGER  REFERENCES tenures (tenure_id),
    house                       SMALLINT,
    ida_agency_id               BIGINT   REFERENCES agencies (agency_id),
    work_category               TEXT,
    activity_name               TEXT,
    official_category           TEXT,   -- parsed tail of activity_name
    work_description            TEXT,
    letter_no                   TEXT,
    work_stage                  TEXT,
    stage_flag                  SMALLINT,
    recommendation_date         DATE,
    sanction_date               DATE,
    actual_end_date             DATE,
    recommended_amount          NUMERIC(18, 2),
    sanction_amount             NUMERIC(18, 2),
    actual_amount               NUMERIC(18, 2),
    average_rating              NUMERIC(4, 2),
    attach_parent_id            BIGINT,
    file_status                 BOOLEAN,
    source_id                   BIGINT REFERENCES sources (source_id),
    UNIQUE (work_recommendation_dtl_id, mp_id)
);
CREATE INDEX IF NOT EXISTS works_state_idx ON works (state_id);
CREATE INDEX IF NOT EXISTS works_mp_idx    ON works (mp_id);

-- One row per vendor payment. This grain does not exist in the CSV snapshot the
-- rest of the project uses; it is only available through the live portal.
CREATE TABLE IF NOT EXISTS payments (
    payment_id                 BIGSERIAL PRIMARY KEY,
    work_ref                   TEXT REFERENCES works (work_ref),
    work_recommendation_dtl_id BIGINT NOT NULL,
    vendor_id                  BIGINT,
    vendor_name                TEXT,
    ia_agency_id               BIGINT REFERENCES agencies (agency_id),
    expenditure_date           DATE,
    fund_disbursed_amount      NUMERIC(18, 2),
    work_status                TEXT,     -- e.g. 'Payment Success'
    source_id                  BIGINT REFERENCES sources (source_id)
);
CREATE INDEX IF NOT EXISTS payments_work_idx ON payments (work_recommendation_dtl_id);

-- Aggregated per work, kept separate from payments so the dashboard's
-- expenditure tile can be reconciled against either grain.
CREATE TABLE IF NOT EXISTS expenditures (
    work_ref                   TEXT PRIMARY KEY REFERENCES works (work_ref),
    total_disbursed            NUMERIC(18, 2),
    payment_count              INTEGER,
    first_expenditure_date     DATE,
    last_expenditure_date      DATE
);

CREATE TABLE IF NOT EXISTS documents (
    document_id                BIGSERIAL PRIMARY KEY,
    work_recommendation_dtl_id BIGINT NOT NULL,
    attach_id                  TEXT   NOT NULL UNIQUE,   -- '<parent>.<child>'
    attach_parent_id           BIGINT,
    stage_flag                 SMALLINT,
    file_name                  TEXT   NOT NULL,
    declared_extension         TEXT,
    sniffed_content_type       TEXT,
    file_size                  BIGINT,
    sha256                     CHAR(64),
    stored_path                TEXT,
    extracted_text_path        TEXT,
    extraction_method          TEXT,     -- 'pdf_text' | 'ocr' | NULL
    source_id                  BIGINT REFERENCES sources (source_id)
);

CREATE TABLE IF NOT EXISTS images (
    image_id                   BIGSERIAL PRIMARY KEY,
    work_recommendation_dtl_id BIGINT NOT NULL,
    attach_id                  TEXT   NOT NULL UNIQUE,
    attach_parent_id           BIGINT,
    stage_flag                 SMALLINT,
    -- The portal does not label BEFORE/DURING/AFTER. This column stays NULL
    -- unless the source itself says so. Do not infer it.
    source_declared_stage      TEXT,
    file_name                  TEXT NOT NULL,
    width                      INTEGER,
    height                     INTEGER,
    mime_type                  TEXT,
    file_size                  BIGINT,
    sha256                     CHAR(64),
    stored_path                TEXT,
    source_id                  BIGINT REFERENCES sources (source_id)
);

CREATE TABLE IF NOT EXISTS citizen_reviews (
    work_review_id             BIGINT PRIMARY KEY,
    work_recommendation_dtl_id BIGINT,
    star_rating                SMALLINT,
    review_detail              TEXT,
    source_id                  BIGINT REFERENCES sources (source_id)
);

-- Portal-published aggregates, kept so Phase 10 can reconcile against them
-- without re-fetching, and so a discrepancy can be re-checked historically.
CREATE TABLE IF NOT EXISTS portal_aggregates (
    aggregate_id BIGSERIAL PRIMARY KEY,
    combo        TEXT        NOT NULL,
    tile_name    TEXT        NOT NULL,
    count_value  BIGINT,
    amount_value NUMERIC(20, 2),
    retrieved_at TIMESTAMPTZ NOT NULL,
    source_id    BIGINT REFERENCES sources (source_id)
);

CREATE TABLE IF NOT EXISTS audit_events (
    audit_id    BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type  TEXT NOT NULL,   -- 'fetch' | 'store' | 'normalize' | 'validate' | 'failure'
    unit_key    TEXT,
    detail      JSONB
);

COMMIT;
