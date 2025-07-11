import uuid
import os
import json
from datetime import datetime

from flask import Blueprint, request, jsonify
from minio import S3Error
from sprout import db
from sprout.models import Dataset, Job, Model, ModelFile, TrainingInfo
from sprout.schemas import JobSchema
from sprout.isolation_forest.model import (
    predict_with_isolation_forest,
    train_isolation_forest_model,
)
from werkzeug.utils import secure_filename

from sprout.storage.storage import MinIOModelStorage
from sprout.isolation_forest.model_config import ModelConfig

job_schema = JobSchema()
jobs_schema = JobSchema(many=True)

job_bp = Blueprint("job_bp", __name__)
ai_bp = Blueprint("ai_bp", __name__)

UPLOAD_FOLDER = "/tmp/uploads"
ALLOWED_EXTENSIONS = {"csv"}
MINIO_URL = "minio://"
BUCKET_NAME = "health"
BUCKET = MINIO_URL + BUCKET_NAME + "/"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# Import Celery task inside the route function to avoid circular dependency
@job_bp.route("/jobs", methods=["POST"])
def create_job():
    from sprout.celery_worker import (
        execute_job,
    )  # Import here to prevent circular import

    import time

    data = request.get_json()
    job_id = f"job_{int(time.time())}"
    new_job = Job(job_id=job_id, params=data.get("params", {}))
    db.session.add(new_job)
    db.session.commit()

    # Trigger Celery task
    execute_job.apply_async(args=[job_id, data.get("params", {})])

    return jsonify({"message": "Job created", "job_id": job_id}), 201


# Get all jobs
@job_bp.route("/jobs", methods=["GET"])
def get_jobs():
    all_jobs = Job.query.all()
    return jobs_schema.jsonify(all_jobs), 200


# Get a single job by ID
@job_bp.route("/jobs/<int:id>", methods=["GET"])
def get_job(id):
    job = Job.query.get_or_404(id)
    return job_schema.jsonify(job), 200


# Update a job
@job_bp.route("/jobs/<int:id>", methods=["PUT"])
def update_job(id):
    job = Job.query.get_or_404(id)
    data = request.get_json()
    job.job_id = data.get("job_id", job.job_id)
    job.params = data.get("params", job.params)
    db.session.commit()
    return job_schema.jsonify(job), 200


# Delete a job
@job_bp.route("/jobs/<int:id>", methods=["DELETE"])
def delete_job(id):
    job = Job.query.get_or_404(id)
    db.session.delete(job)
    db.session.commit()
    return jsonify({"message": "Job deleted"}), 200


# Check Job Status
@job_bp.route("/jobs/<string:job_id>", methods=["GET"])
def get_job_status(job_id):
    job = Job.query.filter_by(job_id=job_id).first()
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return job_schema.jsonify(job), 200


@ai_bp.route("/ai/resource/upload", methods=["POST"])
def run_upload_file():
    """
    REST API endpoint to upload a single file to MinIO and store the information in the database.

    Request parameters:
    - robot_id: Form parameter, robot ID
    - file: File object

    Returns:
    - JSON response containing the upload status and dataset_id
    """
    # Check if the file is included
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"success": False, "error": "Empty file name"}), 400

    # Get robot_id parameter
    robot_id = request.form.get("robot_id")
    if not robot_id:
        return jsonify({"success": False, "error": "Missing robot_id parameter"}), 400

    # Get description
    description = request.form.get("desc")

    if file and allowed_file(file.filename):
        try:
            filename = secure_filename(file.filename)
            # Generate UUID as a unique filename and dataset_id
            dataset_id = str(uuid.uuid4())
            unique_filename = f"{dataset_id}_{filename}"
            temp_file_path = os.path.join(UPLOAD_FOLDER, unique_filename)

            # Save the file to a temporary directory
            file.save(temp_file_path)

            # Upload the file to MinIO using put_object
            file_size = os.stat(temp_file_path).st_size
            storage = MinIOModelStorage()
            with open(temp_file_path, "rb") as file_data:
                storage.upload_model(file_data, BUCKET_NAME, unique_filename)

            # Delete the temporary file after upload
            os.remove(temp_file_path)

            # File path in MinIO
            file_path = f"{BUCKET}/{unique_filename}"

            # Save to database
            new_dataset = Dataset(
                dataset_id=dataset_id,
                file_path=file_path,
                robot_id=robot_id,
                description=description,
                status="Done",
            )

            db.session.add(new_dataset)
            db.session.commit()

            return (
                jsonify(
                    {
                        "success": True,
                        "message": "File upload successful",
                        "dataset_id": dataset_id,
                        "file_path": file_path,
                        "robot_id": robot_id,
                    }
                ),
                201,
            )

        except S3Error as e:
            # Delete the temporary file if an error occurs
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

            return (
                jsonify(
                    {"success": False, "error": f"Error uploading to MinIO: {str(e)}"}
                ),
                500,
            )

        except Exception as e:
            # Ensure the temporary file is cleaned up in case of any error
            if "temp_file_path" in locals() and os.path.exists(temp_file_path):
                os.remove(temp_file_path)

            return jsonify({"success": False, "error": f"Server error: {str(e)}"}), 500
    else:
        return jsonify({"success": False, "error": "Unsupported file type"}), 400


@ai_bp.route("/ai/run", methods=["POST"])
def run_ai_task():
    """
    API Endpoint to trigger an AI task.
    """
    from sprout.celery_worker import run_ai_job

    data = request.get_json()
    params = data.get("params", {})

    # Create a job in the database
    new_job = Job(job_id=str(uuid.uuid4()), params=params, status="PENDING")
    db.session.add(new_job)
    db.session.commit()

    jobs = Job.query.all()
    for job in jobs:
        print(job.id, job.job_id, job.params)

    # Trigger the Celery task
    run_ai_job.apply_async(args=[new_job.id, params])

    return jsonify({"message": "AI job started", "job_id": new_job.id}), 202


@ai_bp.route("/ai/status/<int:job_id>", methods=["GET"])
def get_ai_job_status(job_id):
    """
    API Endpoint to check the status of an AI task.
    """
    job = Job.query.get(job_id)
    if not job:
        return jsonify({"message": "Job not found"}), 404

    return jsonify({"job_id": job.id, "status": job.status, "params": job.params})


@ai_bp.route("/ai/predict", methods=["POST"])
def predict():
    """
    API endpoint to detect anomalies in new data.
    """
    data = request.get_json()
    model_id_value = data.get("model_id")
    model = ModelFile.query.filter_by(
        model_id=model_id_value, file_type="model"
    ).first()
    scaler = ModelFile.query.filter_by(
        model_id=model_id_value, file_type="scaler"
    ).first()
    scores = ModelFile.query.filter_by(
        model_id=model_id_value, file_type="scores"
    ).first()
    training_data = data.get("training_data")
    model_path = model.file_path.replace(BUCKET, "")
    scaler_path = scaler.file_path.replace(BUCKET, "")
    scores_path = scores.file_path.replace(BUCKET, "")

    predict_result = predict_with_isolation_forest(
        model_path, training_data, scaler_path, scores_path
    )
    filtered_data = [sublist[:3] + sublist[5:] for sublist in predict_result.tolist()]
    return (
        jsonify(
            {
                "predict_result": filtered_data,
            }
        ),
        202,
    )


@ai_bp.route("/ai/train", methods=["POST"])
def train():
    """
    API endpoint to train model.
    """
    data = request.get_json()
    dataset_id = data.get("dataset_id")
    if not dataset_id:
        return jsonify({"success": False, "error": "Missing dataset_id parameter"}), 400

    # Get robot_id parameter
    robot_id = data.get("robot_id")
    if not robot_id:
        return jsonify({"success": False, "error": "Missing robot_id parameter"}), 400

    hyperparameter = data.get("hyperparameter")

    if not hyperparameter:
        hyperparameter = ModelConfig()
    else:
        try:
            hyperparameter = ModelConfig.from_json(hyperparameter)

        except (TypeError, ValueError) as e:
            return (
                jsonify(
                    {"success": False, "error": f"Invalid model parameters: {str(e)}"}
                ),
                400,
            )

    dataser_model = Dataset.query.filter_by(
        dataset_id=dataset_id, robot_id=robot_id
    ).first()
    if not dataser_model:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Can't find dataset file, please check dataset_id and robot_id",
                }
            ),
            400,
        )

    file_path = dataser_model.file_path
    features = data.get("features")

    resource_file = file_path.replace(BUCKET, "")
    result = train_isolation_forest_model(
        BUCKET_NAME,
        resource_file,
        features,
        hyperparameter.n_estimators,
        hyperparameter.contamination,
        hyperparameter.random_state,
    )

    model_filename = result["model_filename"]
    scaler_filename = result["scaler_filename"]
    scores_filename = result["scores_filename"]
    model_size = result["model_size"]
    model_hash = result["model_hash"]
    scaler_size = result["scaler_size"]
    scaler_hash = result["scaler_hash"]
    scores_size = result["scores_size"]
    scores_hash = result["scores_hash"]

    new_model = Model(
        name="IsolationForest",
        robot_id=robot_id,
        description="One more model added",
        created_at=datetime.now(),
    )

    new_training = TrainingInfo(
        model=new_model,
        robot_id=new_model.robot_id,
        hyperparameter=hyperparameter.to_json(),
        training_status="complete",
        created_at=datetime.now(),
    )

    file_path = BUCKET + model_filename
    new_model_file = ModelFile(
        model=new_model,
        file_name=model_filename,
        file_type="model",
        file_path=file_path,
        file_size=model_size,
        file_format="joblib",
        file_hash=model_hash,
        created_at=datetime.now(),
    )

    file_path = BUCKET + scaler_filename
    new_scaler_file = ModelFile(
        model=new_model,
        file_name=scaler_filename,
        file_type="scaler",
        file_path=file_path,
        file_size=scaler_size,
        file_format="joblib",
        file_hash=scaler_hash,
        created_at=datetime.now(),
    )

    file_path = BUCKET + scores_filename
    new_scores_file = ModelFile(
        model=new_model,
        file_name=scores_filename,
        file_type="scores",
        file_path=file_path,
        file_size=scores_size,
        file_format="joblib",
        file_hash=scores_hash,
        created_at=datetime.now(),
    )

    db.session.add(new_model)
    db.session.add(new_training)
    db.session.add(new_model_file)
    db.session.add(new_scaler_file)
    db.session.add(new_scores_file)
    db.session.commit()

    return (
        jsonify(
            {
                "train_result": "success",
                "model_id": new_model.model_id,
            }
        ),
        202,
    )


# API used for test
@ai_bp.route("/ai/get", methods=["GET"])
def get():
    models = ModelFile.query.all()

    for model in models:
        print(model.model_id)

    return jsonify({"message": "Done"}), 200
