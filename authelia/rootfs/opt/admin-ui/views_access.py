"""Access control rules (which apps require which level of login)."""

from flask import Blueprint, flash, redirect, render_template, request, url_for

from core import POLICIES, dig, load_config, save_config, split_csv

bp = Blueprint("access", __name__)


@bp.route("/access")
def index():
    config = load_config()
    rules = dig(config, "access_control", "rules", default=[]) or []
    default_policy = dig(config, "access_control", "default_policy",
                         default="one_factor")
    return render_template("access.html", rules=rules,
                           default_policy=default_policy)


@bp.route("/access/default", methods=["POST"])
def default():
    policy = request.form.get("default_policy", "one_factor")
    if policy not in POLICIES:
        flash("Invalid policy.", "error")
        return redirect(url_for("access.index"))
    config = load_config()
    config.setdefault("access_control", {})["default_policy"] = policy
    save_config(config)
    flash("Default policy saved. Restart Authelia to apply.", "success")
    return redirect(url_for("access.index"))


@bp.route("/access/add", methods=["POST"])
def add():
    form = request.form
    domains = split_csv(form.get("domain", ""))
    policy = form.get("policy", "one_factor")
    if not domains:
        flash("At least one domain is required.", "error")
        return redirect(url_for("access.index"))
    if policy not in POLICIES:
        flash("Invalid policy.", "error")
        return redirect(url_for("access.index"))

    rule = {"domain": domains, "policy": policy}
    subjects = split_csv(form.get("subjects", ""))
    if subjects:
        rule["subject"] = subjects
    resources = split_csv(form.get("resources", ""))
    if resources:
        rule["resources"] = resources

    config = load_config()
    config.setdefault("access_control", {}).setdefault("rules", [])
    if config["access_control"]["rules"] is None:
        config["access_control"]["rules"] = []
    config["access_control"]["rules"].append(rule)
    save_config(config)
    flash("Rule added. Restart Authelia to apply.", "success")
    return redirect(url_for("access.index"))


@bp.route("/access/<int:index>/delete", methods=["POST"])
def delete(index):
    config = load_config()
    rules = dig(config, "access_control", "rules", default=[]) or []
    if 0 <= index < len(rules):
        rules.pop(index)
        config["access_control"]["rules"] = rules
        save_config(config)
        flash("Rule deleted. Restart Authelia to apply.", "success")
    else:
        flash("Unknown rule.", "error")
    return redirect(url_for("access.index"))


@bp.route("/access/<int:index>/move", methods=["POST"])
def move(index):
    direction = request.form.get("direction")
    config = load_config()
    rules = dig(config, "access_control", "rules", default=[]) or []
    target = index - 1 if direction == "up" else index + 1
    if 0 <= index < len(rules) and 0 <= target < len(rules):
        rules[index], rules[target] = rules[target], rules[index]
        config["access_control"]["rules"] = rules
        save_config(config)
        flash("Rule order updated. Restart Authelia to apply.", "success")
    return redirect(url_for("access.index"))
