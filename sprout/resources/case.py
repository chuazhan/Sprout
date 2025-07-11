from flask_restful import abort, Resource, reqparse
from sprout import db
from sprout.models import Case


# Parser for incoming POST/PUT data
case_parser = reqparse.RequestParser()
case_parser.add_argument("name", type=str, required=True, help="Name is required")
case_parser.add_argument("robot_id", type=str, required=True, help="robot_id is required")
case_parser.add_argument("case_type", type=str)
case_parser.add_argument("model_name", type=str)
case_parser.add_argument("description", type=str)

class CaseListResource(Resource):
    def get(self):
        cases = Case.query.all()
        return [case.to_dict() for case in cases]

    def post(self):
        args = case_parser.parse_args()
        new_case = Case(**args)
        db.session.add(new_case)
        db.session.commit()
        return new_case.to_dict(), 201

class CaseResource(Resource):
    def get(self, case_id):
        case = Case.query.get(case_id)
        if not case:
            abort(404, message="Case not found")
        return case.to_dict()

    def put(self, case_id):
        case = Case.query.get(case_id)
        if not case:
            abort(404, message="Case not found")
        args = case_parser.parse_args()
        for key, value in args.items():
            setattr(case, key, value)
        db.session.commit()
        return case.to_dict()

    def delete(self, case_id):
        case = Case.query.get(case_id)
        if not case:
            abort(404, message="Case not found")
        db.session.delete(case)
        db.session.commit()
        return {"message": "Deleted successfully"}
