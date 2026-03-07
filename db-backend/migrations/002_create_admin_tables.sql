-- 管理员相关表
-- admins / admin_sessions / admin_user_actions

-- 管理员账号
CREATE TABLE IF NOT EXISTS admins (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('super_admin', 'admin', 'auditor') NOT NULL DEFAULT 'admin',
    status ENUM('active', 'disabled') NOT NULL DEFAULT 'active',
    last_login_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_admin_status_role (status, role)
);

-- 管理员会话
CREATE TABLE IF NOT EXISTS admin_sessions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    admin_id BIGINT NOT NULL,
    refresh_token_hash CHAR(64) NOT NULL UNIQUE,
    ip_address VARCHAR(45) NULL,
    user_agent VARCHAR(255) NULL,
    expires_at DATETIME NOT NULL,
    revoked_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_admin_sessions_admin (admin_id, created_at),
    FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE
);

-- 管理员操作审计
CREATE TABLE IF NOT EXISTS admin_user_actions (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    admin_id BIGINT NOT NULL,
    target_user_id BIGINT NOT NULL,
    action_type ENUM(
        'ban_user', 'unban_user', 'force_logout',
        'reset_password', 'update_profile', 'delete_user'
    ) NOT NULL,
    reason VARCHAR(255) NULL,
    metadata_json JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_admin_action_time (admin_id, created_at),
    INDEX idx_target_action_time (target_user_id, created_at),
    FOREIGN KEY (admin_id) REFERENCES admins(id),
    FOREIGN KEY (target_user_id) REFERENCES users(id)
);
