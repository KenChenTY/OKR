-- Execute as DBA after migration. Replace the login name before provisioning.
-- Do not grant db_owner to the runtime principal.
IF DATABASE_PRINCIPAL_ID(N'okr_runtime') IS NULL
    CREATE ROLE okr_runtime;
GO
GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::dbo TO okr_runtime;
DENY UPDATE, DELETE ON dbo.audit_events TO okr_runtime;
DENY UPDATE, DELETE ON dbo.check_ins TO okr_runtime;
DENY UPDATE, DELETE ON dbo.objective_revisions TO okr_runtime;
DENY UPDATE, DELETE ON dbo.check_in_evidence TO okr_runtime;
DENY UPDATE, DELETE ON dbo.alembic_version TO okr_runtime;
-- People management is protected by System Admin checks in the API.
-- Remove the earlier provisioning-only deny, then allow audited creation/update.
REVOKE INSERT, UPDATE ON dbo.users FROM okr_runtime;
REVOKE INSERT, UPDATE ON dbo.local_credentials FROM okr_runtime;
GRANT INSERT, UPDATE ON dbo.users TO okr_runtime;
GRANT INSERT, UPDATE ON dbo.local_credentials TO okr_runtime;
DENY DELETE ON dbo.users TO okr_runtime;
DENY DELETE ON dbo.local_credentials TO okr_runtime;
DENY INSERT, UPDATE, DELETE ON dbo.org_units TO okr_runtime;
DENY INSERT, UPDATE, DELETE ON dbo.cycles TO okr_runtime;
DENY UPDATE, DELETE ON dbo.score_snapshots TO okr_runtime;
DENY UPDATE, DELETE ON dbo.benefit_verifications TO okr_runtime;
GO
-- The runtime uses transaction-owned sys.sp_getapplock for invariant locks.
-- User provisioning and schema migrations use a separate privileged identity.
-- CREATE USER [DOMAIN\okr-service] FOR LOGIN [DOMAIN\okr-service];
-- ALTER ROLE okr_runtime ADD MEMBER [DOMAIN\okr-service];
