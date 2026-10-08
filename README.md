# Samruddhi — E-Commerce Platform

A Django + HTMX e-commerce platform. Brand name, logo, favicon, tagline, contact details and the default social-share (Open Graph) image are all managed from the dashboard **Site Settings** page — nothing brand-specific is hard-coded.

## Architecture

Every Django app follows a strict layered architecture:

```
app/
├── models.py          # Data layer only
├── selectors.py       # All read queries (optimized)
├── services.py        # All writes and business rules
├── forms.py / serializers.py
├── views.py           # Thin HTTP layer
├── urls.py
├── admin.py
├── signals.py         # Cross-app side effects only
├── templates/<app>/
└── tests/
    ├── test_models.py
    ├── test_selectors.py
    ├── test_services.py
    └── test_views.py
```

## Apps

| App | Responsibility |
|-----|----------------|
| `core` | Shared mixins, currency, Celery tasks |
| `accounts` | Authentication and profiles |
| `catalog` | Products and categories |
| `gifting` | Gift customization (ContentType) |
| `cart` | Shopping cart |
| `checkout` | Checkout flow |
| `orders` | Order lifecycle |
| `payments` | Payment processing |
| `delivery` | Delivery zones and slots |
| `corporate` | B2B corporate accounts |
| `marketing` | Promotions and campaigns |
| `cms` | Content management |
| `notifications` | Email / SMS / WhatsApp |
| `reports` | Analytics and reporting |

## Quick Start

```bash
# 1. Clone and enter the project
cd Flowers

# 2. Create a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — defaults use SQLite for local dev (no PostgreSQL required)

# 5. Apply migrations
python manage.py migrate

# 6. Create a superuser (optional)
python manage.py createsuperuser

# 7. Run the development server
python manage.py runserver
```

Visit `http://127.0.0.1:8000/health/` for a health check and `http://127.0.0.1:8000/admin/` for Django admin.

---

## Phase 1 — Setup & Verification Steps

Run every command below from the project root with your virtual environment activated.

### 1. System check (must pass with zero warnings)

```bash
python manage.py check
```

Expected output: `System check identified no issues (0 silenced).`

### 2. Fresh database migration

```bash
# Remove any existing SQLite database for a truly fresh run
del db.sqlite3          # Windows
# rm db.sqlite3         # Linux/macOS

python manage.py migrate
```

Expected: all migrations apply without errors, including `core.0002_create_role_groups` and `core.0003_seed_default_currency`.

### 3. Verify all 14 apps are installed

```bash
python manage.py shell -c "
from django.conf import settings
apps = ['core','accounts','catalog','gifting','cart','checkout','orders',
        'payments','delivery','corporate','marketing','cms','notifications','reports']
missing = [a for a in apps if a not in settings.INSTALLED_APPS]
assert not missing, f'Missing apps: {missing}'
print('All 14 apps present in INSTALLED_APPS')
"
```

### 4. Verify role groups were created

```bash
python manage.py shell -c "
from django.contrib.auth.models import Group
names = sorted(Group.objects.filter(name__in=['SuperAdmin','StoreAdmin','CorporateManager']).values_list('name', flat=True))
print('Roles:', names)
assert names == ['CorporateManager', 'StoreAdmin', 'SuperAdmin']
"
```

### 5. Verify base mixins are importable

```bash
python manage.py shell -c "
from core.models import TimeStampedModel, SoftDeleteModel, SEOModel, Currency
print('Mixins OK:', TimeStampedModel, SoftDeleteModel, SEOModel, Currency)
"
```

### 6. Run the test suite

```bash
pytest -v
```

All tests must pass, including soft-delete manager tests and selector query-count tests.

### 7. Lint checks (matches CI)

```bash
flake8 .
black --check .
isort --check .
python manage.py makemigrations --check --dry-run
```

### 8. Celery worker — verify a trivial task executes

Start Redis (required for Celery broker):

```bash
# Docker (recommended)
docker run -d --name samruddhi-redis -p 6379:6379 redis:7
```

Terminal 1 — start the Celery worker:

```bash
celery -A config worker --loglevel=info
```

Terminal 2 — dispatch the ping task:

```bash
python manage.py shell -c "
from core.tasks import ping
result = ping.delay()
print('Task ID:', result.id)
print('Result:', result.get(timeout=10))
"
```

Expected output: `Result: pong`

Terminal 3 (optional) — verify the periodic health-check task is registered:

```bash
celery -A config beat --loglevel=info
```

---

## Environment Variables

| Variable | Description | Default (dev) |
|----------|-------------|---------------|
| `DJANGO_SETTINGS_MODULE` | Settings module | `config.settings.dev` |
| `SECRET_KEY` | Django secret key | (required in prod) |
| `DEBUG` | Debug mode | `True` |
| `DATABASE_URL` | PostgreSQL or SQLite URL | SQLite file |
| `REDIS_URL` | Redis cache URL | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL` | Celery broker | `redis://localhost:6379/1` |
| `CELERY_RESULT_BACKEND` | Celery results | `redis://localhost:6379/2` |
| `USE_S3` | Enable AWS S3 media storage | `False` |
| `AWS_*` | S3 credentials and bucket | — |

### PostgreSQL (production / staging)

```env
DATABASE_URL=postgres://samruddhi:samruddhi@localhost:5432/samruddhi
DB_POOL_MIN_SIZE=2
DB_POOL_MAX_SIZE=10
DB_STATEMENT_TIMEOUT_OPTIONS=-c statement_timeout=30000
```

---

## AWS EC2 Deployment

### Prerequisites

- Ubuntu 22.04+ EC2 instance
- PostgreSQL (RDS or local)
- Redis (ElastiCache or local)
- Domain pointed at the instance

### Deploy flow

```bash
# 1. On the EC2 instance — install system packages
sudo apt update && sudo apt install -y python3.11 python3.11-venv nginx postgresql-client redis-tools

# 2. Clone the repository
sudo mkdir -p /var/www/samruddhi
sudo chown $USER:$USER /var/www/samruddhi
git clone <your-repo-url> /var/www/samruddhi
cd /var/www/samruddhi

# 3. Python environment
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Environment configuration
cp .env.example .env
# Edit .env with production values:
#   DJANGO_SETTINGS_MODULE=config.settings.prod
#   DATABASE_URL=postgres://...
#   SECRET_KEY=<strong-random-key>
#   ALLOWED_HOSTS=your-domain.com
#   USE_S3=True (if using S3)

# 5. Collect static files and migrate
python manage.py migrate --noinput
python manage.py collectstatic --noinput

# 6. Install systemd service
sudo cp deploy/systemd/samruddhi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable samruddhi
sudo systemctl start samruddhi
sudo systemctl status samruddhi

# 7. Configure Nginx
sudo cp deploy/nginx/samruddhi.conf /etc/nginx/sites-available/samruddhi
sudo ln -s /etc/nginx/sites-available/samruddhi /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 8. Celery worker + beat (separate systemd units or supervisor)
celery -A config worker --loglevel=info --detach
celery -A config beat --loglevel=info --detach
```

Gunicorn binds to a Unix socket at `/run/samruddhi/gunicorn.sock` (see `deploy/gunicorn/gunicorn.conf.py`). Nginx proxies HTTP traffic to that socket.

---

## CI

GitHub Actions workflow at `.github/workflows/ci.yml` runs on every push/PR:

- `flake8`
- `black --check`
- `isort --check`
- `python manage.py makemigrations --check --dry-run`
- `python manage.py migrate`
- `python manage.py check`
- `pytest`

---

## License

Proprietary — Ecomicx Projects.
