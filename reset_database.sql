-- Drop all tables and recreate schema
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;

-- Create user table
CREATE TABLE "user" (
    id SERIAL PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(128),
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create player table
CREATE TABLE player (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) NOT NULL,
    jersey_number INTEGER,
    position VARCHAR(20),
    gender VARCHAR(20),
    gender_match VARCHAR(20),
    team VARCHAR(64),
    user_id INTEGER REFERENCES "user"(id)
);
