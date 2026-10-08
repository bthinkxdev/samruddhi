import multiprocessing
import os

bind = os.environ.get("GUNICORN_BIND", "unix:/run/samruddhi/gunicorn.sock")
workers = int(os.environ.get("GUNICORN_WORKERS", max(3, multiprocessing.cpu_count() + 1)))
worker_class = "sync"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 120))
keepalive = 5
max_requests = 1000
max_requests_jitter = 50
accesslog = os.environ.get("GUNICORN_ACCESS_LOG", "-")
errorlog = os.environ.get("GUNICORN_ERROR_LOG", "-")
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
capture_output = True
