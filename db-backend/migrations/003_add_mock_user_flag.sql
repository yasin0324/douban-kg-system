SET @has_is_mock := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'users'
      AND COLUMN_NAME = 'is_mock'
);

SET @add_is_mock_sql := IF(
    @has_is_mock = 0,
    'ALTER TABLE users ADD COLUMN is_mock TINYINT(1) NOT NULL DEFAULT 0 AFTER status',
    'SELECT 1'
);

PREPARE stmt FROM @add_is_mock_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @has_is_mock_idx := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'users'
      AND INDEX_NAME = 'idx_users_is_mock_status'
);

SET @add_is_mock_idx_sql := IF(
    @has_is_mock_idx = 0,
    'CREATE INDEX idx_users_is_mock_status ON users (is_mock, status)',
    'SELECT 1'
);

PREPARE stmt FROM @add_is_mock_idx_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
