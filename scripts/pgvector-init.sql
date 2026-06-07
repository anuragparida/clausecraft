-- Enable the pgvector extension on the clausecraft database.
-- This script runs once on first container init (Postgres entrypoint
-- executes /docker-entrypoint-initdb.d/*.sql in alpha order against the
-- POSTGRES_DB named in the container env).
CREATE EXTENSION IF NOT EXISTS vector;
