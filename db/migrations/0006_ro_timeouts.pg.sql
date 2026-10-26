-- PostgreSQL only. Caps what the web role can hold: a slow query or a forgotten transaction would
-- otherwise keep the web app's single connection busy. It is set on the role, not on the web
-- connection, because Neon's pooler rejects startup parameters.
ALTER ROLE voltia_ro SET statement_timeout = '5s';
ALTER ROLE voltia_ro SET idle_in_transaction_session_timeout = '10s';
