from sprout import ma
from sprout.models import Job


class JobSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = Job
        load_instance = True
