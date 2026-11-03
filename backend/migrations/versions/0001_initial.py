"""Initial SQL Server schema, frozen at implementation time."""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE cycles (\n\tname NVARCHAR(100) NOT NULL, \n\tstart_date DATETIME NOT NULL, \n\tend_date DATETIME NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tCHECK (start_date <= end_date), \n\tUNIQUE (name)\n)"
    )
    op.execute(
        "CREATE TABLE idempotency_records (\n\t[key] NVARCHAR(200) NOT NULL, \n\tdigest NVARCHAR(64) NOT NULL, \n\tresponse NVARCHAR(max) NOT NULL, \n\tcreated_at DATETIME2(3) NOT NULL, \n\tPRIMARY KEY ([key])\n)"
    )
    op.execute(
        "CREATE TABLE jobs (\n\tkind NVARCHAR(30) NOT NULL, \n\tpayload NVARCHAR(max) NOT NULL, \n\tdedupe_key NVARCHAR(200) NOT NULL, \n\tstatus NVARCHAR(20) NOT NULL, \n\tattempts INTEGER NOT NULL, \n\tnext_run DATETIME2(3) NOT NULL, \n\tlocked_until DATETIME2(3) NULL, \n\tlock_token NVARCHAR(64) NULL, \n\terror NVARCHAR(1000) NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tUNIQUE (dedupe_key)\n)"
    )
    op.execute("CREATE INDEX ix_jobs_due ON jobs (status, next_run)")
    op.execute(
        "CREATE TABLE login_flows (\n\ttoken_hash NVARCHAR(64) NOT NULL, \n\tpayload NVARCHAR(max) NOT NULL, \n\texpires_at DATETIME2(3) NOT NULL, \n\tPRIMARY KEY (token_hash)\n)"
    )
    op.execute(
        "CREATE TABLE org_units (\n\tname NVARCHAR(100) NOT NULL, \n\tparent_id BIGINT NULL, \n\tunit_type NVARCHAR(30) NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(parent_id) REFERENCES org_units (id)\n)"
    )
    op.execute(
        "CREATE TABLE users (\n\tsubject NVARCHAR(200) NOT NULL, \n\tname NVARCHAR(100) NOT NULL, \n\trole NVARCHAR(30) NOT NULL, \n\torg_id BIGINT NOT NULL, \n\tactive BIT NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tUNIQUE (subject), \n\tFOREIGN KEY(org_id) REFERENCES org_units (id)\n)"
    )
    op.execute(
        "CREATE TABLE app_sessions (\n\ttoken_hash NVARCHAR(64) NOT NULL, \n\tuser_id BIGINT NOT NULL, \n\tcsrf NVARCHAR(100) NOT NULL, \n\texpires_at DATETIME2(3) NOT NULL, \n\tlast_seen DATETIME2(3) NOT NULL, \n\tPRIMARY KEY (token_hash), \n\tFOREIGN KEY(user_id) REFERENCES users (id)\n)"
    )
    op.execute(
        "CREATE TABLE objectives (\n\tcode NVARCHAR(40) NOT NULL, \n\ttitle NVARCHAR(200) NOT NULL, \n\tdescription NVARCHAR(max) NOT NULL, \n\towner_id BIGINT NOT NULL, \n\torg_id BIGINT NOT NULL, \n\tcycle_id BIGINT NOT NULL, \n\ttheme NVARCHAR(100) NOT NULL, \n\tpriority NVARCHAR(20) NOT NULL, \n\tlevel NVARCHAR(20) NOT NULL, \n\tparent_id BIGINT NULL, \n\tstart_date DATETIME NOT NULL, \n\tend_date DATETIME NOT NULL, \n\tstatus NVARCHAR(20) NOT NULL, \n\trevision INTEGER NOT NULL, \n\tcreated_at DATETIME2(3) NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\trow_version ROWVERSION NOT NULL, \n\tPRIMARY KEY (id), \n\tCHECK (start_date <= end_date), \n\tCHECK (status IN ('Draft','Submitted','Approved','Active','Completed','Cancelled','Archived')), \n\tUNIQUE (code), \n\tFOREIGN KEY(owner_id) REFERENCES users (id), \n\tFOREIGN KEY(org_id) REFERENCES org_units (id), \n\tFOREIGN KEY(cycle_id) REFERENCES cycles (id), \n\tFOREIGN KEY(parent_id) REFERENCES objectives (id)\n)"
    )
    op.execute("CREATE INDEX ix_objectives_scope ON objectives (cycle_id, org_id, status)")
    op.execute(
        "CREATE TABLE review_meetings (\n\torg_id BIGINT NOT NULL, \n\tcycle_id BIGINT NOT NULL, \n\ttitle NVARCHAR(200) NOT NULL, \n\tmeeting_at DATETIME2(3) NOT NULL, \n\tdecisions NVARCHAR(max) NOT NULL, \n\trisks VARCHAR(max) NOT NULL, \n\tcreated_by BIGINT NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(org_id) REFERENCES org_units (id), \n\tFOREIGN KEY(cycle_id) REFERENCES cycles (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)"
    )
    op.execute(
        "CREATE TABLE approvals (\n\tobjective_id BIGINT NOT NULL, \n\trevision INTEGER NOT NULL, \n\tstage NVARCHAR(30) NOT NULL, \n\tassignee_id BIGINT NOT NULL, \n\tsubmitted_by BIGINT NOT NULL, \n\tnext_assignee_id BIGINT NULL, \n\tstatus NVARCHAR(20) NOT NULL, \n\tcomment VARCHAR(max) NOT NULL, \n\tdecided_at DATETIME2(3) NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(objective_id) REFERENCES objectives (id), \n\tFOREIGN KEY(assignee_id) REFERENCES users (id), \n\tFOREIGN KEY(submitted_by) REFERENCES users (id), \n\tFOREIGN KEY(next_assignee_id) REFERENCES users (id)\n)"
    )
    op.execute("CREATE INDEX ix_approvals_objective_id ON approvals (objective_id)")
    op.execute("CREATE UNIQUE INDEX uq_approval_pending ON approvals (objective_id) WHERE status = 'Pending'")
    op.execute(
        "CREATE TABLE audit_events (\n\tactor_id BIGINT NOT NULL, \n\taction NVARCHAR(50) NOT NULL, \n\tobjective_id BIGINT NULL, \n\tdetail NVARCHAR(max) NOT NULL, \n\trequest_id NVARCHAR(64) NOT NULL, \n\toccurred_at DATETIME2(3) NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(actor_id) REFERENCES users (id), \n\tFOREIGN KEY(objective_id) REFERENCES objectives (id)\n)"
    )
    op.execute("CREATE INDEX ix_audit_events_occurred_at ON audit_events (occurred_at)")
    op.execute(
        "CREATE TABLE evidence_versions (\n\tobjective_id BIGINT NOT NULL, \n\tprevious_id BIGINT NULL, \n\tname NVARCHAR(255) NOT NULL, \n\tkind NVARCHAR(20) NOT NULL, \n\tstorage_key NVARCHAR(100) NULL, \n\turl NVARCHAR(2000) NULL, \n\tsha256 NVARCHAR(64) NULL, \n\tsize BIGINT NOT NULL, \n\tstatus NVARCHAR(20) NOT NULL, \n\tuploaded_by BIGINT NOT NULL, \n\tuploaded_at DATETIME2(3) NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(objective_id) REFERENCES objectives (id), \n\tFOREIGN KEY(previous_id) REFERENCES evidence_versions (id), \n\tFOREIGN KEY(uploaded_by) REFERENCES users (id)\n)"
    )
    op.execute("CREATE INDEX ix_evidence_versions_objective_id ON evidence_versions (objective_id)")
    op.execute(
        "CREATE TABLE key_results (\n\tobjective_id BIGINT NOT NULL, \n\tname NVARCHAR(200) NOT NULL, \n\tvalue_type NVARCHAR(20) NOT NULL, \n\tdirection NVARCHAR(20) NOT NULL, \n\tbaseline NUMERIC(19, 4) NOT NULL, \n\tcurrent_value NUMERIC(19, 4) NOT NULL, \n\ttarget NUMERIC(19, 4) NOT NULL, \n\tweight NUMERIC(9, 4) NOT NULL, \n\tunit NVARCHAR(30) NOT NULL, \n\tcurrency NVARCHAR(3) NULL, \n\tfrequency NVARCHAR(20) NOT NULL, \n\tconfidence INTEGER NOT NULL, \n\tlast_checkin_at DATETIME2(3) NULL, \n\tnext_due DATETIME NOT NULL, \n\tsevere_blocker BIT NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\trow_version ROWVERSION NOT NULL, \n\tPRIMARY KEY (id), \n\tCHECK (weight > 0 AND weight <= 100), \n\tCHECK (confidence BETWEEN 0 AND 100), \n\tFOREIGN KEY(objective_id) REFERENCES objectives (id)\n)"
    )
    op.execute("CREATE INDEX ix_key_results_objective_id ON key_results (objective_id)")
    op.execute(
        "CREATE TABLE notifications (\n\tuser_id BIGINT NOT NULL, \n\tobjective_id BIGINT NOT NULL, \n\tmessage NVARCHAR(300) NOT NULL, \n\tdedupe_key NVARCHAR(200) NOT NULL, \n\tcreated_at DATETIME2(3) NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tFOREIGN KEY(objective_id) REFERENCES objectives (id), \n\tUNIQUE (dedupe_key)\n)"
    )
    op.execute(
        "CREATE TABLE objective_relations (\n\tsource_id BIGINT NOT NULL, \n\ttarget_id BIGINT NOT NULL, \n\tkind NVARCHAR(30) NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tUNIQUE (source_id, target_id, kind), \n\tCHECK (source_id <> target_id), \n\tFOREIGN KEY(source_id) REFERENCES objectives (id), \n\tFOREIGN KEY(target_id) REFERENCES objectives (id)\n)"
    )
    op.execute(
        "CREATE TABLE objective_revisions (\n\tobjective_id BIGINT NOT NULL, \n\trevision INTEGER NOT NULL, \n\tsnapshot NVARCHAR(max) NOT NULL, \n\tcreated_at DATETIME2(3) NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tUNIQUE (objective_id, revision), \n\tFOREIGN KEY(objective_id) REFERENCES objectives (id)\n)"
    )
    op.execute(
        "CREATE TABLE review_actions (\n\tmeeting_id BIGINT NOT NULL, \n\ttitle NVARCHAR(200) NOT NULL, \n\towner_id BIGINT NOT NULL, \n\tdue_date DATETIME NOT NULL, \n\tstatus NVARCHAR(20) NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(meeting_id) REFERENCES review_meetings (id), \n\tFOREIGN KEY(owner_id) REFERENCES users (id)\n)"
    )
    op.execute(
        "CREATE TABLE check_ins (\n\tkr_id BIGINT NOT NULL, \n\tactor_id BIGINT NOT NULL, \n\tcurrent_value NUMERIC(19, 4) NOT NULL, \n\tconfidence INTEGER NOT NULL, \n\tcommentary NVARCHAR(max) NOT NULL, \n\trisks VARCHAR(max) NOT NULL, \n\tblockers VARCHAR(max) NOT NULL, \n\tnext_action VARCHAR(max) NOT NULL, \n\teffective_at DATETIME2(3) NOT NULL, \n\tsubmitted_at DATETIME2(3) NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(kr_id) REFERENCES key_results (id), \n\tFOREIGN KEY(actor_id) REFERENCES users (id)\n)"
    )
    op.execute("CREATE INDEX ix_check_ins_kr_id ON check_ins (kr_id)")
    op.execute(
        "CREATE TABLE milestones (\n\tkr_id BIGINT NOT NULL, \n\tname NVARCHAR(200) NOT NULL, \n\tweight NUMERIC(9, 4) NOT NULL, \n\tdue_date DATETIME NOT NULL, \n\taccepted_at DATETIME2(3) NULL, \n\taccepted_by BIGINT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tCHECK (weight > 0), \n\tFOREIGN KEY(kr_id) REFERENCES key_results (id), \n\tFOREIGN KEY(accepted_by) REFERENCES users (id)\n)"
    )
    op.execute("CREATE INDEX ix_milestones_kr_id ON milestones (kr_id)")
    op.execute(
        "CREATE TABLE check_in_evidence (\n\tcheckin_id BIGINT NOT NULL, \n\tevidence_id BIGINT NOT NULL, \n\tPRIMARY KEY (checkin_id, evidence_id), \n\tFOREIGN KEY(checkin_id) REFERENCES check_ins (id), \n\tFOREIGN KEY(evidence_id) REFERENCES evidence_versions (id)\n)"
    )


def downgrade():
    raise RuntimeError("Initial schema rollback is destructive; restore a verified backup instead")
