-- PostgreSQL only. Creates the role used by the web app.
-- The role cannot write data tables. It may write rate_limits, which the chat endpoint needs.
-- Enable login and set a password by hand, never in this file:
--   ALTER ROLE voltia_ro WITH LOGIN PASSWORD '<generated-password>';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'voltia_ro') THEN
        CREATE ROLE voltia_ro NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO voltia_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO voltia_ro;
GRANT INSERT, UPDATE, DELETE ON rate_limits TO voltia_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO voltia_ro;
