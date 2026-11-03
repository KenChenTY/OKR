-- Review-only SQL Server schema. Deploy with Alembic to retain version tracking.

CREATE TABLE cycles (
	name NVARCHAR(100) NOT NULL, 
	start_date DATETIME NOT NULL, 
	end_date DATETIME NOT NULL, 
	id BIGINT NOT NULL IDENTITY, 
	PRIMARY KEY (id), 
	CHECK (start_date <= end_date), 
	UNIQUE (name)
)
GO

CREATE TABLE idempotency_records (
	[key] NVARCHAR(200) NOT NULL, 
	digest NVARCHAR(64) NOT NULL, 
	response NVARCHAR(max) NOT NULL, 
	created_at DATETIME2(3) NOT NULL, 
	PRIMARY KEY ([key])
)
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
)
GO

CREATE INDEX ix_jobs_due ON jobs (status, next_run)
GO

CREATE TABLE login_flows (
	token_hash NVARCHAR(64) NOT NULL, 
	payload NVARCHAR(max) NOT NULL, 
	expires_at DATETIME2(3) NOT NULL, 
	PRIMARY KEY (token_hash)
)
GO

CREATE TABLE org_units (
	name NVARCHAR(100) NOT NULL, 
	parent_id BIGINT NULL, 
	unit_type NVARCHAR(30) NOT NULL, 
	id BIGINT NOT NULL IDENTITY, 
	PRIMARY KEY (id), 
	FOREIGN KEY(parent_id) REFERENCES org_units (id)
)
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
)
GO

CREATE TABLE app_sessions (
	token_hash NVARCHAR(64) NOT NULL, 
	user_id BIGINT NOT NULL, 
	csrf NVARCHAR(100) NOT NULL, 
	expires_at DATETIME2(3) NOT NULL, 
	last_seen DATETIME2(3) NOT NULL, 
	PRIMARY KEY (token_hash), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)
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
)
GO

CREATE INDEX ix_objectives_scope ON objectives (cycle_id, org_id, status)
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
)
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
)
GO

CREATE INDEX ix_approvals_objective_id ON approvals (objective_id)
GO

CREATE UNIQUE INDEX uq_approval_pending ON approvals (objective_id) WHERE status = 'Pending'
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
)
GO

CREATE INDEX ix_audit_events_occurred_at ON audit_events (occurred_at)
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
)
GO

CREATE INDEX ix_evidence_versions_objective_id ON evidence_versions (objective_id)
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
)
GO

CREATE INDEX ix_key_results_objective_id ON key_results (objective_id)
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
)
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
)
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
)
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
)
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
)
GO

CREATE INDEX ix_check_ins_kr_id ON check_ins (kr_id)
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
)
GO

CREATE INDEX ix_milestones_kr_id ON milestones (kr_id)
GO

CREATE TABLE check_in_evidence (
	checkin_id BIGINT NOT NULL, 
	evidence_id BIGINT NOT NULL, 
	PRIMARY KEY (checkin_id, evidence_id), 
	FOREIGN KEY(checkin_id) REFERENCES check_ins (id), 
	FOREIGN KEY(evidence_id) REFERENCES evidence_versions (id)
)
GO
