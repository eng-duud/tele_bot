bot: python manage.py run_all_bots
web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
worker: celery -A config worker -l info
