-- ==========================================================
-- Skema Database: Smart Visitor AI Agent
-- Database: visitor_management
-- ==========================================================

CREATE DATABASE IF NOT EXISTS `visitor_management` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `visitor_management`;

-- ----------------------------------------------------------
-- 1. Tabel visitors (Data Pengunjung)
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS `visitors` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `nama` VARCHAR(150) NOT NULL,
    `jenis_identitas` VARCHAR(50) NOT NULL,
    `nomor_identitas` VARCHAR(100) NOT NULL,
    `no_hp` VARCHAR(50) NOT NULL,
    `instansi` VARCHAR(150) NOT NULL,
    `bertemu_dengan` VARCHAR(150) NOT NULL,
    `keperluan` TEXT NOT NULL,
    `check_in` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `check_out` DATETIME NULL DEFAULT NULL,
    `status` VARCHAR(50) NOT NULL DEFAULT 'SEDANG BERKUNJUNG',
    `status_kartu` VARCHAR(50) NOT NULL DEFAULT 'TIDAK',
    INDEX `idx_nomor_identitas` (`nomor_identitas`),
    INDEX `idx_check_in` (`check_in`),
    INDEX `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------
-- 2. Tabel staff_accounts (Akun Petugas / Admin)
-- ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS `staff_accounts` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `nama` VARCHAR(150) NOT NULL,
    `username` VARCHAR(100) NOT NULL UNIQUE,
    `password` VARCHAR(255) NOT NULL,
    `role` VARCHAR(50) NOT NULL DEFAULT 'petugas',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ----------------------------------------------------------
-- Akun Default Petugas (Username: admin, Password: admin123)
-- ----------------------------------------------------------
INSERT INTO `staff_accounts` (`nama`, `username`, `password`, `role`)
VALUES ('Administrator', 'admin', 'admin123', 'admin')
ON DUPLICATE KEY UPDATE `username` = `username`;
