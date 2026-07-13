"""Advanced page: raw YAML editor with validation."""

import os
import shutil

import yaml
from flask import Blueprint, flash, redirect, render_template, request, url_for

from core import CONFIG_PATH, mark_restart_needed, validate_config_file

bp = Blueprint("advanced", __name__)


@bp.route("/editor", methods=["GET", "POST"])
def editor():
    if request.method == "POST":
        content = request.form.get("content", "")
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as exc:
            flash(f"YAML syntax error: {exc}", "error")
            return render_template("editor.html", content=content)

        tmp_path = "/tmp/authelia_config_candidate.yml"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        ok, output = validate_config_file(tmp_path)
        if not ok:
            flash(f"Authelia rejected the configuration: {output}", "error")
            return render_template("editor.html", content=content)

        if os.path.exists(CONFIG_PATH):
            shutil.copy2(CONFIG_PATH, CONFIG_PATH + ".bak")
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(CONFIG_PATH, 0o600)
        mark_restart_needed()
        flash("Configuration saved. Restart Authelia to apply.", "success")
        return redirect(url_for("advanced.editor"))

    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            content = fh.read()
    except FileNotFoundError:
        content = ""
    return render_template("editor.html", content=content)
