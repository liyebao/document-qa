-- Bootstrap the local PostgreSQL instance when Docker is not used.
-- Run as a superuser from the repository root:
--   psql -U postgres -f backend/scripts/init_local_db.sql
--
-- Creates the qa/qa account (same credentials as docker-compose.yml) plus the
-- document_qa and document_qa_test databases. Safe to re-run: existing roles and
-- databases are skipped.
--
-- The account is granted SUPERUSER on purpose: alembic migrations create the
-- vector and pg_trgm extensions, which requires superuser rights. Docker does the
-- same, since POSTGRES_USER is a superuser there as well. Keep the instance bound
-- to 127.0.0.1 and never reuse these credentials outside local development.
--
-- pgvector is NOT installed by this script. If it is missing, the first
-- `alembic upgrade head` fails with "extension \"vector\" is not available".

\set ON_ERROR_STOP on

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'qa') THEN
        CREATE ROLE qa LOGIN PASSWORD 'qa' SUPERUSER;
    END IF;
END
$$;

SELECT 'CREATE DATABASE document_qa OWNER qa'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'document_qa')\gexec

SELECT 'CREATE DATABASE document_qa_test OWNER qa'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'document_qa_test')\gexec
