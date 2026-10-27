-- Run once as the postgres superuser, e.g.:
--   psql -U postgres -h localhost -f scripts/init_postgres.sql
-- Replace 'change-me' with your own password and put the same value in server/.env.
CREATE ROLE lognexa WITH LOGIN PASSWORD 'change-me';
CREATE DATABASE lognexa OWNER lognexa;
