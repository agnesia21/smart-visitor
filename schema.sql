-- ==========================================================
-- Skema Database: Smart Visitor AI Agent
-- Database: PostgreSQL (Supabase)
-- ==========================================================

-- ----------------------------------------------------------
-- 1. Tabel visitors (Data Pengunjung)
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS visitors (
    id SERIAL PRIMARY KEY,
    nama VARCHAR(150) NOT NULL,
    jenis_identitas VARCHAR(50) NOT NULL,
    nomor_identitas VARCHAR(100) NOT NULL,
    no_hp VARCHAR(50) NOT NULL,
    instansi VARCHAR(150) NOT NULL,
    bertemu_dengan VARCHAR(150) NOT NULL,
    keperluan TEXT NOT NULL,
    check_in TIMESTAMP NOT NULL DEFAULT NOW(),
    check_out TIMESTAMP NULL DEFAULT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'checked_in',
    status_kartu VARCHAR(50) NOT NULL DEFAULT 'tidak_dititipkan'
);

CREATE INDEX IF NOT EXISTS idx_visitors_nomor_identitas ON visitors (nomor_identitas);
CREATE INDEX IF NOT EXISTS idx_visitors_check_in ON visitors (check_in);
CREATE INDEX IF NOT EXISTS idx_visitors_status ON visitors (status);

-- ----------------------------------------------------------
-- 2. Tabel staff_accounts (Akun Petugas / Admin)
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS staff_accounts (
    id SERIAL PRIMARY KEY,
    nama VARCHAR(150) NOT NULL,
    username VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'petugas',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------
-- Akun Default Petugas (Username: admin, Password: admin123)
-- ----------------------------------------------------------
INSERT INTO staff_accounts (nama, username, password, role)
VALUES ('Administrator', 'admin', 'admin123', 'admin')
ON CONFLICT (username) DO NOTHING;
