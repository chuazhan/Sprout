from sprout import db
from sqlalchemy.dialects.postgresql import JSON, VARCHAR
import uuid
from datetime import datetime


class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(80), unique=True, nullable=False)
    params = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(50), default="PENDING")

    def __repr__(self):
        return f"<Job {self.job_id}>"

class Case(db.Model):
    __tablename__ = "cases"

    case_id = db.Column(
        db.String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    name = db.Column(db.String(255), nullable=False)
    robot_id = db.Column(db.String(255), nullable=False)
    case_type = db.Column(db.String(48), default="health_profile")
    model_name = db.Column(db.String(48), default="IsolationForest")
    description = db.Column(db.Text)
    created_at = db.Column(db.TIMESTAMP, default=datetime.now)

    models = db.relationship(
        "Model", back_populates="case", cascade="all, delete-orphan"
    )

    training_info = db.relationship(
        "TrainingInfo", back_populates="case", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Case {self.name}>"

    def to_dict(self):
        return {
            "case_id": self.case_id,
            "name": self.name,
            "robot_id": self.robot_id,
            "case_type": self.case_type,
            "model_name": self.model_name,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

class Dataset(db.Model):
    __tablename__ = "datasets"

    dataset_id = db.Column(
        db.String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    file_path = db.Column(db.Text, nullable=False)
    robot_id = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(48), default="pending")
    created_at = db.Column(db.TIMESTAMP, default=datetime.now)
    description = db.Column(db.Text)

    def __repr__(self):
        return f"<Dataset {self.file_path} - {self.status}>"


class Model(db.Model):
    __tablename__ = "models"

    model_id = db.Column(
        VARCHAR(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name = db.Column(db.String(255), nullable=False)
    robot_id = db.Column(db.String(255), nullable=False)
    case_id = db.Column(db.String(36), db.ForeignKey("cases.case_id"))
    description = db.Column(db.Text)
    created_at = db.Column(db.TIMESTAMP, default=datetime.now)
    dataset_id = db.Column(db.String(36))

    case = db.relationship("Case", back_populates="models")

    training_info = db.relationship(
        "TrainingInfo", back_populates="model", cascade="all, delete-orphan"
    )
    model_files = db.relationship(
        "ModelFile", back_populates="model", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Model {self.name}>"


class TrainingInfo(db.Model):
    __tablename__ = "training_info"

    training_id = db.Column(
        VARCHAR(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    model_id = db.Column(VARCHAR(36), db.ForeignKey("models.model_id"), nullable=False)
    robot_id = db.Column(db.String(255), nullable=False)
    case_id = db.Column(db.String(36), db.ForeignKey("cases.case_id"))
    hyperparameter = db.Column(JSON, nullable=False)
    training_status = db.Column(db.String(48), default="pending")
    created_at = db.Column(db.TIMESTAMP, default=datetime.now)
    started_at = db.Column(db.TIMESTAMP)
    completed_at = db.Column(db.TIMESTAMP)

    model = db.relationship("Model", back_populates="training_info")

    case = db.relationship("Case", back_populates="training_info")

    def __repr__(self):
        return f"<TrainingInfo {self.training_id} - {self.training_status}>"


class ModelFile(db.Model):
    __tablename__ = "model_files"

    file_id = db.Column(
        VARCHAR(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    model_id = db.Column(VARCHAR(36), db.ForeignKey("models.model_id"), nullable=False)
    file_name = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(48), default="training_data")
    file_path = db.Column(db.Text, nullable=False)
    file_size = db.Column(db.BigInteger, nullable=False)
    file_format = db.Column(db.String(32), nullable=False)
    file_hash = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.TIMESTAMP, default=datetime.now)

    model = db.relationship("Model", back_populates="model_files")

    def __repr__(self):
        return f"<ModelFile {self.file_name}>"

class HyperParameter(db.Model):
    __tablename__ = "hyper_parameters"

    param_id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    model_name = db.Column(db.String(48), default="IsolationForest")
    param_key = db.Column(db.String(48))
    description = db.Column(db.Text)

    values = db.relationship("HyperParameterValue", back_populates="param", cascade="all, delete-orphan")


class HyperParameterValue(db.Model):
    __tablename__ = "hyper_parameter_values"
    
    value_id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    param_id = db.Column(db.String(36), db.ForeignKey("hyper_parameters.param_id"))
    param_value = db.Column(db.String(255), nullable=False)

    param = db.relationship("HyperParameter", back_populates="values")
