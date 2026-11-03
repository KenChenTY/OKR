"""Add initiatives, project links, benefits and independent verification."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE benefits (\n\tobjective_id BIGINT NOT NULL, \n\treference NVARCHAR(100) NOT NULL, \n\tname NVARCHAR(200) NOT NULL, \n\tcategory NVARCHAR(30) NOT NULL, \n\tunit NVARCHAR(30) NOT NULL, \n\tcurrency NVARCHAR(3) NULL, \n\tperiod_start DATETIME NOT NULL, \n\tperiod_end DATETIME NOT NULL, \n\tmethod NVARCHAR(max) NOT NULL, \n\tcreated_by BIGINT NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tCHECK (period_start <= period_end), \n\tFOREIGN KEY(objective_id) REFERENCES objectives (id), \n\tUNIQUE (reference), \n\tFOREIGN KEY(created_by) REFERENCES users (id)\n)"
    )
    op.execute("CREATE INDEX ix_benefits_objective_id ON benefits (objective_id)")
    op.execute(
        "CREATE TABLE benefit_allocations (\n\tbenefit_id BIGINT NOT NULL, \n\tobjective_id BIGINT NOT NULL, \n\tshare NUMERIC(9, 4) NOT NULL, \n\tPRIMARY KEY (benefit_id, objective_id), \n\tCHECK (share > 0 AND share <= 100), \n\tFOREIGN KEY(benefit_id) REFERENCES benefits (id), \n\tFOREIGN KEY(objective_id) REFERENCES objectives (id)\n)"
    )
    op.execute(
        "CREATE TABLE benefit_claims (\n\tbenefit_id BIGINT NOT NULL, \n\tclaimed_value NUMERIC(19, 4) NULL, \n\tnarrative NVARCHAR(max) NOT NULL, \n\tevidence_id BIGINT NOT NULL, \n\tsubmitted_by BIGINT NOT NULL, \n\tsubmitted_at DATETIME2(3) NOT NULL, \n\tstatus NVARCHAR(20) NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tCHECK (claimed_value IS NULL OR claimed_value >= 0), \n\tFOREIGN KEY(benefit_id) REFERENCES benefits (id), \n\tFOREIGN KEY(evidence_id) REFERENCES evidence_versions (id), \n\tFOREIGN KEY(submitted_by) REFERENCES users (id)\n)"
    )
    op.execute("CREATE INDEX ix_benefit_claims_benefit_id ON benefit_claims (benefit_id)")
    op.execute("CREATE UNIQUE INDEX uq_benefit_pending_claim ON benefit_claims (benefit_id) WHERE status = 'Pending'")
    op.execute(
        "CREATE TABLE initiatives (\n\tkr_id BIGINT NOT NULL, \n\towner_id BIGINT NOT NULL, \n\ttitle NVARCHAR(200) NOT NULL, \n\tdescription NVARCHAR(max) NOT NULL, \n\tstatus NVARCHAR(20) NOT NULL, \n\tstart_date DATETIME NOT NULL, \n\tend_date DATETIME NOT NULL, \n\tactual_end_date DATETIME NULL, \n\teffort_hours NUMERIC(19, 4) NOT NULL, \n\tinvestment NUMERIC(19, 4) NOT NULL, \n\tcurrency NVARCHAR(3) NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\trow_version ROWVERSION NOT NULL, \n\tPRIMARY KEY (id), \n\tCHECK (start_date <= end_date), \n\tCHECK (effort_hours >= 0 AND investment >= 0), \n\tCHECK (status IN ('Planned','InProgress','Completed','Cancelled')), \n\tFOREIGN KEY(kr_id) REFERENCES key_results (id), \n\tFOREIGN KEY(owner_id) REFERENCES users (id)\n)"
    )
    op.execute("CREATE INDEX ix_initiatives_kr_id ON initiatives (kr_id)")
    op.execute(
        "CREATE TABLE benefit_verifications (\n\tclaim_id BIGINT NOT NULL, \n\tverified_value NUMERIC(19, 4) NULL, \n\treviewer_id BIGINT NOT NULL, \n\tdecision NVARCHAR(20) NOT NULL, \n\tcomment NVARCHAR(max) NOT NULL, \n\tverified_at DATETIME2(3) NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tCHECK (verified_value IS NULL OR verified_value >= 0), \n\tUNIQUE (claim_id), \n\tFOREIGN KEY(claim_id) REFERENCES benefit_claims (id), \n\tFOREIGN KEY(reviewer_id) REFERENCES users (id)\n)"
    )
    op.execute(
        "CREATE TABLE external_project_links (\n\tinitiative_id BIGINT NOT NULL, \n\tsystem NVARCHAR(30) NOT NULL, \n\texternal_id NVARCHAR(200) NOT NULL, \n\turl NVARCHAR(2000) NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tUNIQUE (initiative_id, system, external_id), \n\tFOREIGN KEY(initiative_id) REFERENCES initiatives (id)\n)"
    )


def downgrade():
    raise RuntimeError("Benefit evidence and verification history must not be discarded")
