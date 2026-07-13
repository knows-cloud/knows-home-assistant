"""User management for the file authentication backend."""

import re

from flask import Blueprint, flash, redirect, render_template, request, url_for

from core import hash_password, load_users, save_users, split_csv

bp = Blueprint("users", __name__)

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{1,64}$")


@bp.route("/users")
def index():
    data = load_users()
    return render_template("users.html", users=data["users"])


@bp.route("/users/add", methods=["POST"])
def add():
    form = request.form
    username = form.get("username", "").strip()
    password = form.get("password", "")
    if not USERNAME_RE.match(username):
        flash("Invalid username (letters, digits, . _ - only).", "error")
        return redirect(url_for("users.index"))
    if len(password) < 8:
        flash("Password must be at least 8 characters.", "error")
        return redirect(url_for("users.index"))

    data = load_users()
    if username in data["users"]:
        flash(f"User '{username}' already exists.", "error")
        return redirect(url_for("users.index"))

    try:
        digest = hash_password(password)
    except Exception as exc:  # noqa: BLE001
        flash(f"Password hashing failed: {exc}", "error")
        return redirect(url_for("users.index"))

    data["users"][username] = {
        "disabled": False,
        "displayname": form.get("displayname", "").strip() or username,
        "email": form.get("email", "").strip(),
        "password": digest,
        "groups": split_csv(form.get("groups", "")),
    }
    save_users(data)
    flash(f"User '{username}' created. Restart Authelia to apply.", "success")
    return redirect(url_for("users.index"))


@bp.route("/users/<username>/edit", methods=["POST"])
def edit(username):
    form = request.form
    data = load_users()
    if username not in data["users"]:
        flash(f"Unknown user '{username}'.", "error")
        return redirect(url_for("users.index"))
    user = data["users"][username]
    user["displayname"] = form.get("displayname", "").strip() or username
    user["email"] = form.get("email", "").strip()
    user["groups"] = split_csv(form.get("groups", ""))
    save_users(data)
    flash(f"User '{username}' updated. Restart Authelia to apply.", "success")
    return redirect(url_for("users.index"))


@bp.route("/users/<username>/password", methods=["POST"])
def password(username):
    new_password = request.form.get("password", "")
    if len(new_password) < 8:
        flash("Password must be at least 8 characters.", "error")
        return redirect(url_for("users.index"))
    data = load_users()
    if username not in data["users"]:
        flash(f"Unknown user '{username}'.", "error")
        return redirect(url_for("users.index"))
    try:
        data["users"][username]["password"] = hash_password(new_password)
    except Exception as exc:  # noqa: BLE001
        flash(f"Password hashing failed: {exc}", "error")
        return redirect(url_for("users.index"))
    save_users(data)
    flash(f"Password for '{username}' updated. Restart Authelia to apply.",
          "success")
    return redirect(url_for("users.index"))


@bp.route("/users/<username>/toggle", methods=["POST"])
def toggle(username):
    data = load_users()
    if username not in data["users"]:
        flash(f"Unknown user '{username}'.", "error")
        return redirect(url_for("users.index"))
    user = data["users"][username]
    user["disabled"] = not user.get("disabled", False)
    save_users(data)
    state = "disabled" if user["disabled"] else "enabled"
    flash(f"User '{username}' {state}. Restart Authelia to apply.", "success")
    return redirect(url_for("users.index"))


@bp.route("/users/<username>/delete", methods=["POST"])
def delete(username):
    data = load_users()
    if username not in data["users"]:
        flash(f"Unknown user '{username}'.", "error")
        return redirect(url_for("users.index"))
    if len(data["users"]) == 1:
        flash("Refusing to delete the last remaining user.", "error")
        return redirect(url_for("users.index"))
    del data["users"][username]
    save_users(data)
    flash(f"User '{username}' deleted. Restart Authelia to apply.", "success")
    return redirect(url_for("users.index"))
