from app.workers.celery_app import celery_app


@celery_app.task(name="apflow.healthcheck")
def healthcheck() -> str:
    return "ok"
