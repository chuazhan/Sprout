import time
from sprout import celery
from sprout import create_app

from sprout import db
from sprout.models import Job


@celery.task(bind=True)
def run_ai_job(self, job_id, params):
    """
    Celery task for running AI-related jobs.
    """
    app = create_app()
    with app.app_context():
        job = Job.query.get(job_id)
        if job:
            try:
                # Simulate AI processing (or make a call to an external API)
                time.sleep(5)  # Simulate processing time

                # Mock AI processing, Calling the AI method in future.
                ai_result = {"output": f"Processed with params {params}"}

                job.status = "COMPLETED"
                job.params["result"] = ai_result
                db.session.commit()
                return ai_result
            except Exception as e:
                job.status = "FAILED"
                db.session.commit()
                raise self.retry(exc=e)


@celery.task
def scheduled_task():
    print("Task executed!")
    # Todo: Calling the AI method in future.
    return "Task completed successfully"
