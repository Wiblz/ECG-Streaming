# Database Migrations

This directory contains yoyo-migrations database migrations for the ECG Aggregator.

## Migration History

- **0001**: Initial schema (all base tables: ecg_samples, accelerometer_samples, sessions, devices, collectors, device_collector_mappings)
- **0002**: Add session_id column to ecg_samples table
- **0003**: Add session_id column to accelerometer_samples table
- **0004**: Add magnitude column to accelerometer_samples table
- **0005**: Add nickname column to devices table

## How Migrations Work

Migrations are automatically applied when `ECGDatabase` is initialized. The system:
1. Detects if this is an existing database (has tables but no yoyo tracking)
2. For legacy databases, marks all migrations as applied without re-running them
3. For new databases or databases with yoyo tracking, applies pending migrations

## Creating New Migrations

When you need to add a new migration:

1. Create a new file with the next sequential number: `0006_description.py`
2. Import `step` from yoyo
3. Add a dependency on the previous migration using `__depends__`
4. Define steps with apply and optional rollback SQL
5. Test locally before committing

Example:
```python
"""
Brief description of what this migration does.
"""

from yoyo import step

__depends__ = {"0005_add_nickname_to_devices"}

steps = [
    step(
        "CREATE INDEX idx_example ON table_name(column_name)",
        "DROP INDEX idx_example"
    ),
]
```

## Rollback Limitations

SQLite has limited ALTER TABLE support:
- Cannot DROP COLUMN (until SQLite 3.35.0)
- Cannot ALTER COLUMN type or constraints
- Cannot DROP constraints

For this reason, migrations 0002-0005 do not have rollback support (rollback is `None`). For complex schema changes requiring rollback, use table recreation patterns.

## Manual Migration Management

While migrations are applied automatically, you can also use the yoyo CLI:

### List migrations
```bash
yoyo list --database sqlite:////absolute/path/to/ecg_data.db ./migrations
```

### Apply migrations
```bash
yoyo apply --database sqlite:////absolute/path/to/ecg_data.db ./migrations
```

### Rollback migrations
```bash
yoyo rollback --database sqlite:////absolute/path/to/ecg_data.db ./migrations
```

## Best Practices

1. **Never modify existing migrations** after they've been committed to version control
2. **Never delete migration files** - this will break the migration history
3. **Never reorder migration numbers** - the sequence must remain stable
4. **Always test migrations** on a copy of your database first
5. **Commit migrations with code changes** that depend on the schema changes
6. **Add descriptive docstrings** to explain what each migration does and why

## Migration Dependencies

Migrations use `__depends__` to declare dependencies on previous migrations. This ensures migrations are applied in the correct order and prevents conflicts.
