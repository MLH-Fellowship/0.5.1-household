from flask import Blueprint, request, jsonify
from models import User
from app import db
from flask_jwt_extended import create_access_token
from sqlalchemy.exc import DatabaseError
from app.utils import error_missing_json_key

auth_blueprint = Blueprint("auth", __name__, url_prefix="/auth")


@auth_blueprint.route("/register")
def register():
    username = request.json["username"]
    email = request.json["email"]
    password = request.json["password"]
    if (not username) or (not email) or (not password):
        return error_missing_json_key("username", "email", "password")
    new_user = User(email=email, username=username, email_verified=False)
    new_user.set_password(password)
    db.session.add(new_user)
    try:
        db.session.commit()
    except DatabaseError as error:
        return jsonify({"msg": "Couldn't create a new user. Failed with error: '{}'".format(error)}), 500
    db.session.refresh(new_user)
    return jsonify({"msg": "Created a new user", "data": new_user.id})


@auth_blueprint.route("/login")
def login():
    identifier = request.json["identifier"]
    password = request.json["password"]
    if (not identifier) or (not password):
        return error_missing_json_key("identifier", "password")
    user: User = User.query.filter(
        User.username == identifier | User.email == identifier).first()
    if not user:
        return jsonify({"msg": "A user with those details does not exist."}), 403
    if user.check_password(password):
        access_token = create_access_token(identity=user.id)
        return jsonify(access_token=access_token), 200
    else:
        return jsonify({"msg": "The provided password is incorrect."}), 403
