import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('gui_spector_webapp')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Periodic tasks
app.conf.beat_schedule = {
    'reap-display-leases-every-minute': {
        'task': 'setups.tasks.reap_display_leases',
        'schedule': crontab(minute='*/1'),
    }
}