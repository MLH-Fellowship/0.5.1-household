from flask import Blueprint, request, jsonify, render_template, url_for, current_app, g
from app.models import User
from app import db
from flask_jwt_extended import create_access_token
from sqlalchemy.exc import DatabaseError
from app.utils import error_missing_json_key
import jwt
import os
from app.utils import send_email
import time
import datetime

auth_blueprint = Blueprint(
    "auth", __name__, url_prefix="/auth", template_folder="/templates"
)


@auth_blueprint.route("/register", methods=("POST",))
def register():
    try:
        username = request.json["username"]
        email = request.json["email"]
        password = request.json["password"]
    except KeyError:
        return error_missing_json_key("username", "email", "password")
    new_user = User(email=email, username=username, email_verified=False)
    new_user.set_password(password)
    db.session.add(new_user)
    try:
        db.session.commit()
    except DatabaseError as error:
        return (
            jsonify(
                {
                    "msg": "Couldn't create a new user. Failed with error: '{}'".format(
                        error
                    )
                }
            ),
            500,
        )
    db.session.refresh(new_user)
    verify_email_url = url_for(
        "auth.verify_email",
        token=jwt.encode(
            {
                "token_type": "verify_email",
                "user_id": new_user.id,
                "exp": (
                    datetime.datetime.utcnow() + datetime.timedelta(seconds=3600)
                ).timestamp(),
            },
            current_app.secret_key,
        ),
        _external=not current_app.testing,
    )
    html_content = render_template(
        "email_verify.jinja", verify_email_url=verify_email_url
    )
    send_email(
        new_user.email,
        "Verify your email.",
        html_content,
        "Follow this link to verify your email: {}".format(verify_email_url),
    )
    return jsonify(
        {"msg": "Created a new user.", "data": new_user.id, "status": "success"}
    )


@auth_blueprint.route("/login", methods=("POST",))
def login():
    try:
        # either the user's username or email
        identifier = request.json["identifier"]
        password = request.json["password"]
    except KeyError:
        return error_missing_json_key("identifier", "password")
    user: User = User.query.filter(
        (User.username == identifier) | (User.email == identifier)
    ).first()

    if not user:
        return jsonify({"msg": "A user with those details does not exist."}), 403

    if not user.check_password(password):
        return (
            jsonify({"msg": "The provided password is incorrect.", "status": "error"}),
            403,
        )

    data = {}
    data["username"] = user.username
    try:
        data["access_token"] = create_access_token(
            identity=user.id,
            expires_delta=datetime.timedelta(seconds=request.json["custom_expiry"]),
        )
    except KeyError:
        data["access_token"] = create_access_token(identity=user.id)

    return jsonify(data=data, status="success", msg=""), 200


@auth_blueprint.route("/password_reset/reset_form/<string:token>")
def reset_password_form(token):
    try:
        token = jwt.decode(token, current_app.secret_key)
    except jwt.DecodeError:
        return "That token isn't valid."
    return render_template(
        "password_reset.jinja",
        password_reset_submit=url_for(
            "auth.perform_reset", token=token, _external=not current_app.testing
        ),
    )


@auth_blueprint.route("/password_reset/<string:identifier>")
def reset_password(identifier):
    user: User = User.query.filter(
        (User.username == identifier) | (User.email == identifier)
    ).first()
    if not user:
        return {"msg": "That user does not exist.", "status": "error", "data": ""}
    reset_link = url_for(
        "auth.reset_password_form",
        token=jwt.encode(
            {
                "user_id": user.id,
                "token_type": "reset_password",
                "exp": time.time() + 3600,
            },
            current_app.secret_key,
        ),
        _external=not current_app.testing,
    )
    html_content = render_template("password_email_reset.jinja", reset_link=reset_link)
    send_email(
        user.email,
        "Reset your password.",
        html_content,
        "Follow this link to reset your password: {}".format(reset_link),
    )
    return "Check your inbox for a password reset."


@auth_blueprint.route("/password_reset/reset/<string:token>", methods=("POST",))
def perform_reset(token):
    password = request.form["password"]
    password2 = request.form["password2"]
    if password != password2:
        return "Your new passwords don't match"
    try:
        token = jwt.decode(token, current_app.secret_key)
    except jwt.DecodeError:
        return "The token supplied is not valid."
    try:
        if token["token_type"] == "reset_password":
            user: User = User.query.get(token["user_id"])
            user.set_password(password)
            db.session.commit()
            return "Your password has been reset."
        else:
            return "The token supplied is not valid."
    except TypeError:
        return "The token supplied is not valid."


@auth_blueprint.route("/verify_email/<string:token>")
def verify_email(token):
    try:
        token = jwt.decode(token, current_app.secret_key)
        if token["token_type"] == "verify_email":
            user: User = User.query.get(token["user_id"])
            user.email_verified = True
            db.session.commit()
            return "Successfully verified your email."
    except jwt.DecodeError:
        return "The token supplied is not valid.", 400
