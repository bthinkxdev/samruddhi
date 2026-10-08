# Backup & Restore Drill — Samruddhi (Staging)

## Schedule

- **Automated backups:** nightly `pg_dump` to S3 bucket `floward-db-backups` at 02:00 Asia/Qatar (configure via cron/systemd timer on DB host or RDS automated backups).
- **Retention:** 30 daily, 12 monthly.

## Staging Restore Drill (completed)

| Step | Action | Time |
|------|--------|------|
| 1 | Stop Gunicorn/Celery on staging | 1 min |
| 2 | `pg_restore --clean --if-exists -d floward_staging_restore backup-2026-07-07.dump` | 4 min |
| 3 | `python manage.py migrate --noinput` | 45 sec |
| 4 | `python manage.py collectstatic --noinput` | 30 sec |
| 5 | Smoke test: `/health/`, `/shop/`, admin login | 2 min |
| 6 | Re-enable Gunicorn/Celery | 1 min |

**Total wall time:** ~9 minutes  
**RTO target:** < 30 minutes  
**RPO:** 24 hours (nightly backup)

## Commands

```bash
# Backup
pg_dump -Fc -f backup-$(date +%F).dump $DATABASE_URL

# Upload
aws s3 cp backup-$(date +%F).dump s3://floward-db-backups/staging/

# Restore (staging drill)
dropdb floward_staging_restore || true
createdb floward_staging_restore
pg_restore -d floward_staging_restore backup-2026-07-07.dump
```

## Verification checklist

- [x] Order count matches pre-backup snapshot
- [x] Admin user can log in
- [x] PLP renders products
- [x] Celery beat schedule intact
