"""Add approved changes, object readers, exports and score history."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE exports (\n\tuser_id BIGINT NOT NULL, \n\tcycle_id BIGINT NULL, \n\tstatus NVARCHAR(20) NOT NULL, \n\tstorage_key NVARCHAR(100) NOT NULL, \n\tobject_ids NVARCHAR(max) NOT NULL, \n\tcreated_at DATETIME2(3) NOT NULL, \n\texpires_at DATETIME2(3) NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tFOREIGN KEY(cycle_id) REFERENCES cycles (id)\n)"
    )
    op.execute(
        "CREATE TABLE change_requests (\n\tobjective_id BIGINT NOT NULL, \n\tproposed NVARCHAR(max) NOT NULL, \n\treason NVARCHAR(max) NOT NULL, \n\tstage NVARCHAR(30) NOT NULL, \n\tstatus NVARCHAR(20) NOT NULL, \n\tsubmitted_by BIGINT NOT NULL, \n\tassignee_id BIGINT NOT NULL, \n\tnext_assignee_id BIGINT NOT NULL, \n\tdecisions NVARCHAR(max) NOT NULL, \n\tcreated_at DATETIME2(3) NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(objective_id) REFERENCES objectives (id), \n\tFOREIGN KEY(submitted_by) REFERENCES users (id), \n\tFOREIGN KEY(assignee_id) REFERENCES users (id), \n\tFOREIGN KEY(next_assignee_id) REFERENCES users (id)\n)"
    )
    op.execute("CREATE UNIQUE INDEX uq_change_pending ON change_requests (objective_id) WHERE status = 'Pending'")
    op.execute(
        "CREATE TABLE objective_grants (\n\tobjective_id BIGINT NOT NULL, \n\tuser_id BIGINT NOT NULL, \n\tgranted_by BIGINT NOT NULL, \n\tPRIMARY KEY (objective_id, user_id), \n\tFOREIGN KEY(objective_id) REFERENCES objectives (id), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tFOREIGN KEY(granted_by) REFERENCES users (id)\n)"
    )
    op.execute(
        "CREATE TABLE score_snapshots (\n\tobjective_id BIGINT NOT NULL, \n\tsnapshot_date DATETIME NOT NULL, \n\tformula_version NVARCHAR(20) NOT NULL, \n\tpayload NVARCHAR(max) NOT NULL, \n\tid BIGINT NOT NULL IDENTITY, \n\tPRIMARY KEY (id), \n\tUNIQUE (objective_id, snapshot_date), \n\tFOREIGN KEY(objective_id) REFERENCES objectives (id)\n)"
    )


def downgrade():
    raise RuntimeError("Governance history must not be discarded; restore a verified backup")
