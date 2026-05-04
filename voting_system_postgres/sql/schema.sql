CREATE TABLE IF NOT EXISTS voters (
    id BIGSERIAL PRIMARY KEY,
    voter_id VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(20) NOT NULL UNIQUE,
    age INTEGER NOT NULL CHECK (age >= 18 AND age <= 120),
    constituency VARCHAR(120) NOT NULL,
    address TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'voter' CHECK (role IN ('voter', 'admin')),
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    phone_verified BOOLEAN NOT NULL DEFAULT FALSE,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    proof_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (proof_status IN ('pending', 'approved', 'rejected')),
    proof_filename TEXT,
    proof_original_name TEXT,
    photo_filename TEXT,
    has_voted BOOLEAN NOT NULL DEFAULT FALSE,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS candidates (
    id BIGSERIAL PRIMARY KEY,
    candidate_id VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(20) NOT NULL UNIQUE,
    age INTEGER NOT NULL CHECK (age >= 18 AND age <= 120),
    constituency VARCHAR(120) NOT NULL,
    party VARCHAR(120) NOT NULL,
    symbol VARCHAR(120) NOT NULL,
    manifesto TEXT,
    password_hash TEXT NOT NULL,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    phone_verified BOOLEAN NOT NULL DEFAULT FALSE,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    proof_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (proof_status IN ('pending', 'approved', 'rejected')),
    proof_filename TEXT,
    proof_original_name TEXT,
    photo_filename TEXT,
    votes INTEGER NOT NULL DEFAULT 0,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS otp_codes (
    id BIGSERIAL PRIMARY KEY,
    account_type VARCHAR(20) NOT NULL CHECK (account_type IN ('voter', 'candidate')),
    public_id VARCHAR(20) NOT NULL,
    purpose VARCHAR(40) NOT NULL DEFAULT 'registration',
    delivery_target TEXT,
    otp_hash TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS votes (
    id BIGSERIAL PRIMARY KEY,
    voter_db_id BIGINT NOT NULL REFERENCES voters(id) ON DELETE CASCADE,
    candidate_db_id BIGINT NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    constituency VARCHAR(120) NOT NULL,
    vote_receipt_hash TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT one_vote_per_voter UNIQUE (voter_db_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    actor_role VARCHAR(30) NOT NULL,
    actor_identifier VARCHAR(80) NOT NULL,
    action VARCHAR(80) NOT NULL,
    details TEXT,
    ip_address VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Safe upgrades for old databases created from earlier versions.
ALTER TABLE voters ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE voters ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE voters ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
ALTER TABLE otp_codes ADD COLUMN IF NOT EXISTS delivery_target TEXT;
ALTER TABLE votes ADD COLUMN IF NOT EXISTS vote_receipt_hash TEXT NOT NULL DEFAULT '';

-- Preserve previously verified accounts when upgrading.
UPDATE voters SET email_verified = TRUE, phone_verified = TRUE WHERE is_verified = TRUE;
UPDATE candidates SET email_verified = TRUE, phone_verified = TRUE WHERE is_verified = TRUE;

CREATE UNIQUE INDEX IF NOT EXISTS idx_voters_phone_unique ON voters(phone);
CREATE UNIQUE INDEX IF NOT EXISTS idx_candidates_phone_unique ON candidates(phone);
CREATE INDEX IF NOT EXISTS idx_voters_constituency ON voters(constituency);
CREATE INDEX IF NOT EXISTS idx_voters_proof_status ON voters(proof_status);
CREATE INDEX IF NOT EXISTS idx_candidates_constituency ON candidates(constituency);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON candidates(status);
CREATE INDEX IF NOT EXISTS idx_otp_lookup ON otp_codes(account_type, public_id, purpose, consumed_at, expires_at);
CREATE INDEX IF NOT EXISTS idx_votes_candidate ON votes(candidate_db_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);

INSERT INTO settings (key, value) VALUES
('election_enabled', 'false'),
('election_start', ''),
('election_end', ''),
('public_results_enabled', 'true'),
('assistant_enabled', 'true')
ON CONFLICT (key) DO NOTHING;
