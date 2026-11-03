BEGIN TRANSACTION;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

GO

-- Running upgrade  -> 0001

CREATE TABLE cycles (
    name NVARCHAR(100) NOT NULL, 
    start_date DATETIME NOT NULL, 
    end_date DATETIME NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    CHECK (start_date <= end_date), 
    UNIQUE (name)
);

GO

CREATE TABLE idempotency_records (
    [key] NVARCHAR(200) NOT NULL, 
    digest NVARCHAR(64) NOT NULL, 
    response NVARCHAR(max) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    PRIMARY KEY ([key])
);

GO

CREATE TABLE jobs (
    kind NVARCHAR(30) NOT NULL, 
    payload NVARCHAR(max) NOT NULL, 
    dedupe_key NVARCHAR(200) NOT NULL, 
    status NVARCHAR(20) NOT NULL, 
    attempts INTEGER NOT NULL, 
    next_run DATETIME2(3) NOT NULL, 
    locked_until DATETIME2(3) NULL, 
    lock_token NVARCHAR(64) NULL, 
    error NVARCHAR(1000) NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    UNIQUE (dedupe_key)
);

GO

CREATE INDEX ix_jobs_due ON jobs (status, next_run);

GO

CREATE TABLE login_flows (
    token_hash NVARCHAR(64) NOT NULL, 
    payload NVARCHAR(max) NOT NULL, 
    expires_at DATETIME2(3) NOT NULL, 
    PRIMARY KEY (token_hash)
);

GO

CREATE TABLE org_units (
    name NVARCHAR(100) NOT NULL, 
    parent_id BIGINT NULL, 
    unit_type NVARCHAR(30) NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    FOREIGN KEY(parent_id) REFERENCES org_units (id)
);

GO

CREATE TABLE users (
    subject NVARCHAR(200) NOT NULL, 
    name NVARCHAR(100) NOT NULL, 
    role NVARCHAR(30) NOT NULL, 
    org_id BIGINT NOT NULL, 
    active BIT NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    UNIQUE (subject), 
    FOREIGN KEY(org_id) REFERENCES org_units (id)
);

GO

CREATE TABLE app_sessions (
    token_hash NVARCHAR(64) NOT NULL, 
    user_id BIGINT NOT NULL, 
    csrf NVARCHAR(100) NOT NULL, 
    expires_at DATETIME2(3) NOT NULL, 
    last_seen DATETIME2(3) NOT NULL, 
    PRIMARY KEY (token_hash), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

GO

CREATE TABLE objectives (
    code NVARCHAR(40) NOT NULL, 
    title NVARCHAR(200) NOT NULL, 
    description NVARCHAR(max) NOT NULL, 
    owner_id BIGINT NOT NULL, 
    org_id BIGINT NOT NULL, 
    cycle_id BIGINT NOT NULL, 
    theme NVARCHAR(100) NOT NULL, 
    priority NVARCHAR(20) NOT NULL, 
    level NVARCHAR(20) NOT NULL, 
    parent_id BIGINT NULL, 
    start_date DATETIME NOT NULL, 
    end_date DATETIME NOT NULL, 
    status NVARCHAR(20) NOT NULL, 
    revision INTEGER NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    row_version ROWVERSION NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (start_date <= end_date), 
    CHECK (status IN ('Draft','Submitted','Approved','Active','Completed','Cancelled','Archived')), 
    UNIQUE (code), 
    FOREIGN KEY(owner_id) REFERENCES users (id), 
    FOREIGN KEY(org_id) REFERENCES org_units (id), 
    FOREIGN KEY(cycle_id) REFERENCES cycles (id), 
    FOREIGN KEY(parent_id) REFERENCES objectives (id)
);

GO

CREATE INDEX ix_objectives_scope ON objectives (cycle_id, org_id, status);

GO

CREATE TABLE review_meetings (
    org_id BIGINT NOT NULL, 
    cycle_id BIGINT NOT NULL, 
    title NVARCHAR(200) NOT NULL, 
    meeting_at DATETIME2(3) NOT NULL, 
    decisions NVARCHAR(max) NOT NULL, 
    risks VARCHAR(max) NOT NULL, 
    created_by BIGINT NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    FOREIGN KEY(org_id) REFERENCES org_units (id), 
    FOREIGN KEY(cycle_id) REFERENCES cycles (id), 
    FOREIGN KEY(created_by) REFERENCES users (id)
);

GO

CREATE TABLE approvals (
    objective_id BIGINT NOT NULL, 
    revision INTEGER NOT NULL, 
    stage NVARCHAR(30) NOT NULL, 
    assignee_id BIGINT NOT NULL, 
    submitted_by BIGINT NOT NULL, 
    next_assignee_id BIGINT NULL, 
    status NVARCHAR(20) NOT NULL, 
    comment VARCHAR(max) NOT NULL, 
    decided_at DATETIME2(3) NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    FOREIGN KEY(objective_id) REFERENCES objectives (id), 
    FOREIGN KEY(assignee_id) REFERENCES users (id), 
    FOREIGN KEY(submitted_by) REFERENCES users (id), 
    FOREIGN KEY(next_assignee_id) REFERENCES users (id)
);

GO

CREATE INDEX ix_approvals_objective_id ON approvals (objective_id);

GO

CREATE UNIQUE INDEX uq_approval_pending ON approvals (objective_id) WHERE status = 'Pending';

GO

CREATE TABLE audit_events (
    actor_id BIGINT NOT NULL, 
    action NVARCHAR(50) NOT NULL, 
    objective_id BIGINT NULL, 
    detail NVARCHAR(max) NOT NULL, 
    request_id NVARCHAR(64) NOT NULL, 
    occurred_at DATETIME2(3) NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    FOREIGN KEY(actor_id) REFERENCES users (id), 
    FOREIGN KEY(objective_id) REFERENCES objectives (id)
);

GO

CREATE INDEX ix_audit_events_occurred_at ON audit_events (occurred_at);

GO

CREATE TABLE evidence_versions (
    objective_id BIGINT NOT NULL, 
    previous_id BIGINT NULL, 
    name NVARCHAR(255) NOT NULL, 
    kind NVARCHAR(20) NOT NULL, 
    storage_key NVARCHAR(100) NULL, 
    url NVARCHAR(2000) NULL, 
    sha256 NVARCHAR(64) NULL, 
    size BIGINT NOT NULL, 
    status NVARCHAR(20) NOT NULL, 
    uploaded_by BIGINT NOT NULL, 
    uploaded_at DATETIME2(3) NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    FOREIGN KEY(objective_id) REFERENCES objectives (id), 
    FOREIGN KEY(previous_id) REFERENCES evidence_versions (id), 
    FOREIGN KEY(uploaded_by) REFERENCES users (id)
);

GO

CREATE INDEX ix_evidence_versions_objective_id ON evidence_versions (objective_id);

GO

CREATE TABLE key_results (
    objective_id BIGINT NOT NULL, 
    name NVARCHAR(200) NOT NULL, 
    value_type NVARCHAR(20) NOT NULL, 
    direction NVARCHAR(20) NOT NULL, 
    baseline NUMERIC(19, 4) NOT NULL, 
    current_value NUMERIC(19, 4) NOT NULL, 
    target NUMERIC(19, 4) NOT NULL, 
    weight NUMERIC(9, 4) NOT NULL, 
    unit NVARCHAR(30) NOT NULL, 
    currency NVARCHAR(3) NULL, 
    frequency NVARCHAR(20) NOT NULL, 
    confidence INTEGER NOT NULL, 
    last_checkin_at DATETIME2(3) NULL, 
    next_due DATETIME NOT NULL, 
    severe_blocker BIT NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    row_version ROWVERSION NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (weight > 0 AND weight <= 100), 
    CHECK (confidence BETWEEN 0 AND 100), 
    FOREIGN KEY(objective_id) REFERENCES objectives (id)
);

GO

CREATE INDEX ix_key_results_objective_id ON key_results (objective_id);

GO

CREATE TABLE notifications (
    user_id BIGINT NOT NULL, 
    objective_id BIGINT NOT NULL, 
    message NVARCHAR(300) NOT NULL, 
    dedupe_key NVARCHAR(200) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    FOREIGN KEY(objective_id) REFERENCES objectives (id), 
    UNIQUE (dedupe_key)
);

GO

CREATE TABLE objective_relations (
    source_id BIGINT NOT NULL, 
    target_id BIGINT NOT NULL, 
    kind NVARCHAR(30) NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    UNIQUE (source_id, target_id, kind), 
    CHECK (source_id <> target_id), 
    FOREIGN KEY(source_id) REFERENCES objectives (id), 
    FOREIGN KEY(target_id) REFERENCES objectives (id)
);

GO

CREATE TABLE objective_revisions (
    objective_id BIGINT NOT NULL, 
    revision INTEGER NOT NULL, 
    snapshot NVARCHAR(max) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    UNIQUE (objective_id, revision), 
    FOREIGN KEY(objective_id) REFERENCES objectives (id)
);

GO

CREATE TABLE review_actions (
    meeting_id BIGINT NOT NULL, 
    title NVARCHAR(200) NOT NULL, 
    owner_id BIGINT NOT NULL, 
    due_date DATETIME NOT NULL, 
    status NVARCHAR(20) NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    FOREIGN KEY(meeting_id) REFERENCES review_meetings (id), 
    FOREIGN KEY(owner_id) REFERENCES users (id)
);

GO

CREATE TABLE check_ins (
    kr_id BIGINT NOT NULL, 
    actor_id BIGINT NOT NULL, 
    current_value NUMERIC(19, 4) NOT NULL, 
    confidence INTEGER NOT NULL, 
    commentary NVARCHAR(max) NOT NULL, 
    risks VARCHAR(max) NOT NULL, 
    blockers VARCHAR(max) NOT NULL, 
    next_action VARCHAR(max) NOT NULL, 
    effective_at DATETIME2(3) NOT NULL, 
    submitted_at DATETIME2(3) NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    FOREIGN KEY(kr_id) REFERENCES key_results (id), 
    FOREIGN KEY(actor_id) REFERENCES users (id)
);

GO

CREATE INDEX ix_check_ins_kr_id ON check_ins (kr_id);

GO

CREATE TABLE milestones (
    kr_id BIGINT NOT NULL, 
    name NVARCHAR(200) NOT NULL, 
    weight NUMERIC(9, 4) NOT NULL, 
    due_date DATETIME NOT NULL, 
    accepted_at DATETIME2(3) NULL, 
    accepted_by BIGINT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    CHECK (weight > 0), 
    FOREIGN KEY(kr_id) REFERENCES key_results (id), 
    FOREIGN KEY(accepted_by) REFERENCES users (id)
);

GO

CREATE INDEX ix_milestones_kr_id ON milestones (kr_id);

GO

CREATE TABLE check_in_evidence (
    checkin_id BIGINT NOT NULL, 
    evidence_id BIGINT NOT NULL, 
    PRIMARY KEY (checkin_id, evidence_id), 
    FOREIGN KEY(checkin_id) REFERENCES check_ins (id), 
    FOREIGN KEY(evidence_id) REFERENCES evidence_versions (id)
);

GO

INSERT INTO alembic_version (version_num) OUTPUT inserted.version_num VALUES ('0001');

GO

-- Running upgrade 0001 -> 0002

CREATE TABLE exports (
    user_id BIGINT NOT NULL, 
    cycle_id BIGINT NULL, 
    status NVARCHAR(20) NOT NULL, 
    storage_key NVARCHAR(100) NOT NULL, 
    object_ids NVARCHAR(max) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    expires_at DATETIME2(3) NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    FOREIGN KEY(cycle_id) REFERENCES cycles (id)
);

GO

CREATE TABLE change_requests (
    objective_id BIGINT NOT NULL, 
    proposed NVARCHAR(max) NOT NULL, 
    reason NVARCHAR(max) NOT NULL, 
    stage NVARCHAR(30) NOT NULL, 
    status NVARCHAR(20) NOT NULL, 
    submitted_by BIGINT NOT NULL, 
    assignee_id BIGINT NOT NULL, 
    next_assignee_id BIGINT NOT NULL, 
    decisions NVARCHAR(max) NOT NULL, 
    created_at DATETIME2(3) NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    FOREIGN KEY(objective_id) REFERENCES objectives (id), 
    FOREIGN KEY(submitted_by) REFERENCES users (id), 
    FOREIGN KEY(assignee_id) REFERENCES users (id), 
    FOREIGN KEY(next_assignee_id) REFERENCES users (id)
);

GO

CREATE UNIQUE INDEX uq_change_pending ON change_requests (objective_id) WHERE status = 'Pending';

GO

CREATE TABLE objective_grants (
    objective_id BIGINT NOT NULL, 
    user_id BIGINT NOT NULL, 
    granted_by BIGINT NOT NULL, 
    PRIMARY KEY (objective_id, user_id), 
    FOREIGN KEY(objective_id) REFERENCES objectives (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    FOREIGN KEY(granted_by) REFERENCES users (id)
);

GO

CREATE TABLE score_snapshots (
    objective_id BIGINT NOT NULL, 
    snapshot_date DATETIME NOT NULL, 
    formula_version NVARCHAR(20) NOT NULL, 
    payload NVARCHAR(max) NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    UNIQUE (objective_id, snapshot_date), 
    FOREIGN KEY(objective_id) REFERENCES objectives (id)
);

GO

UPDATE alembic_version SET version_num='0002' WHERE alembic_version.version_num = '0001';

GO

-- Running upgrade 0002 -> 0003

CREATE TABLE benefits (
    objective_id BIGINT NOT NULL, 
    reference NVARCHAR(100) NOT NULL, 
    name NVARCHAR(200) NOT NULL, 
    category NVARCHAR(30) NOT NULL, 
    unit NVARCHAR(30) NOT NULL, 
    currency NVARCHAR(3) NULL, 
    period_start DATETIME NOT NULL, 
    period_end DATETIME NOT NULL, 
    method NVARCHAR(max) NOT NULL, 
    created_by BIGINT NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    CHECK (period_start <= period_end), 
    FOREIGN KEY(objective_id) REFERENCES objectives (id), 
    UNIQUE (reference), 
    FOREIGN KEY(created_by) REFERENCES users (id)
);

GO

CREATE INDEX ix_benefits_objective_id ON benefits (objective_id);

GO

CREATE TABLE benefit_allocations (
    benefit_id BIGINT NOT NULL, 
    objective_id BIGINT NOT NULL, 
    share NUMERIC(9, 4) NOT NULL, 
    PRIMARY KEY (benefit_id, objective_id), 
    CHECK (share > 0 AND share <= 100), 
    FOREIGN KEY(benefit_id) REFERENCES benefits (id), 
    FOREIGN KEY(objective_id) REFERENCES objectives (id)
);

GO

CREATE TABLE benefit_claims (
    benefit_id BIGINT NOT NULL, 
    claimed_value NUMERIC(19, 4) NULL, 
    narrative NVARCHAR(max) NOT NULL, 
    evidence_id BIGINT NOT NULL, 
    submitted_by BIGINT NOT NULL, 
    submitted_at DATETIME2(3) NOT NULL, 
    status NVARCHAR(20) NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    CHECK (claimed_value IS NULL OR claimed_value >= 0), 
    FOREIGN KEY(benefit_id) REFERENCES benefits (id), 
    FOREIGN KEY(evidence_id) REFERENCES evidence_versions (id), 
    FOREIGN KEY(submitted_by) REFERENCES users (id)
);

GO

CREATE INDEX ix_benefit_claims_benefit_id ON benefit_claims (benefit_id);

GO

CREATE UNIQUE INDEX uq_benefit_pending_claim ON benefit_claims (benefit_id) WHERE status = 'Pending';

GO

CREATE TABLE initiatives (
    kr_id BIGINT NOT NULL, 
    owner_id BIGINT NOT NULL, 
    title NVARCHAR(200) NOT NULL, 
    description NVARCHAR(max) NOT NULL, 
    status NVARCHAR(20) NOT NULL, 
    start_date DATETIME NOT NULL, 
    end_date DATETIME NOT NULL, 
    actual_end_date DATETIME NULL, 
    effort_hours NUMERIC(19, 4) NOT NULL, 
    investment NUMERIC(19, 4) NOT NULL, 
    currency NVARCHAR(3) NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    row_version ROWVERSION NOT NULL, 
    PRIMARY KEY (id), 
    CHECK (start_date <= end_date), 
    CHECK (effort_hours >= 0 AND investment >= 0), 
    CHECK (status IN ('Planned','InProgress','Completed','Cancelled')), 
    FOREIGN KEY(kr_id) REFERENCES key_results (id), 
    FOREIGN KEY(owner_id) REFERENCES users (id)
);

GO

CREATE INDEX ix_initiatives_kr_id ON initiatives (kr_id);

GO

CREATE TABLE benefit_verifications (
    claim_id BIGINT NOT NULL, 
    verified_value NUMERIC(19, 4) NULL, 
    reviewer_id BIGINT NOT NULL, 
    decision NVARCHAR(20) NOT NULL, 
    comment NVARCHAR(max) NOT NULL, 
    verified_at DATETIME2(3) NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    CHECK (verified_value IS NULL OR verified_value >= 0), 
    UNIQUE (claim_id), 
    FOREIGN KEY(claim_id) REFERENCES benefit_claims (id), 
    FOREIGN KEY(reviewer_id) REFERENCES users (id)
);

GO

CREATE TABLE external_project_links (
    initiative_id BIGINT NOT NULL, 
    system NVARCHAR(30) NOT NULL, 
    external_id NVARCHAR(200) NOT NULL, 
    url NVARCHAR(2000) NOT NULL, 
    id BIGINT NOT NULL IDENTITY, 
    PRIMARY KEY (id), 
    UNIQUE (initiative_id, system, external_id), 
    FOREIGN KEY(initiative_id) REFERENCES initiatives (id)
);

GO

UPDATE alembic_version SET version_num='0003' WHERE alembic_version.version_num = '0002';

GO

-- Running upgrade 0003 -> 0004

ALTER TABLE objectives ADD visibility NVARCHAR(20) NOT NULL DEFAULT N'organization';

GO

ALTER TABLE objectives ADD CONSTRAINT ck_objective_visibility CHECK (visibility IN ('organization','restricted'));

GO

ALTER TABLE key_results ADD evidence_source NVARCHAR(255) NOT NULL DEFAULT N'人工更新';

GO

UPDATE alembic_version SET version_num='0004' WHERE alembic_version.version_num = '0003';

GO

-- Running upgrade 0004 -> 0005

CREATE TABLE local_credentials (
    user_id BIGINT NOT NULL, 
    username NVARCHAR(64) NOT NULL, 
    password_hash NVARCHAR(255) NOT NULL, 
    PRIMARY KEY (user_id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    UNIQUE (username)
);

GO

CREATE TABLE login_attempts (
    [key] NVARCHAR(64) NOT NULL, 
    failures INTEGER NOT NULL, 
    window_start DATETIME2(3) NOT NULL, 
    PRIMARY KEY ([key])
);

GO

UPDATE alembic_version SET version_num='0005' WHERE alembic_version.version_num = '0004';

GO

-- Running upgrade 0005 -> 0006

ALTER TABLE benefits ADD kr_id BIGINT NULL;

GO

ALTER TABLE benefits ADD CONSTRAINT fk_benefits_kr FOREIGN KEY(kr_id) REFERENCES key_results (id);

GO

CREATE INDEX ix_benefits_kr_id ON benefits (kr_id);

GO

CREATE TABLE quarterly_reviews (
    id BIGINT NOT NULL IDENTITY, 
    objective_id BIGINT NOT NULL, 
    reviewer_id BIGINT NOT NULL, 
    due_date DATETIME NOT NULL, 
    status NVARCHAR(20) NOT NULL, 
    summary NTEXT NOT NULL, 
    lessons NTEXT NOT NULL, 
    next_steps NTEXT NOT NULL, 
    completed_at DATETIME2(3) NULL, 
    PRIMARY KEY (id), 
    CHECK (status IN ('Pending','Completed')), 
    UNIQUE (objective_id), 
    FOREIGN KEY(objective_id) REFERENCES objectives (id), 
    FOREIGN KEY(reviewer_id) REFERENCES users (id)
);

GO

CREATE TABLE strategic_assessments (
    objective_id BIGINT NOT NULL, 
    score INTEGER NOT NULL, 
    rationale NTEXT NOT NULL, 
    assessed_by BIGINT NOT NULL, 
    assessed_at DATETIME2(3) NOT NULL, 
    PRIMARY KEY (objective_id), 
    CHECK (score >= 0 AND score <= 100), 
    FOREIGN KEY(objective_id) REFERENCES objectives (id), 
    FOREIGN KEY(assessed_by) REFERENCES users (id)
);

GO

UPDATE alembic_version SET version_num='0006' WHERE alembic_version.version_num = '0005';

GO

COMMIT;

GO

