"""Branding: portal theme, logo, favicon and custom portal CSS."""

import os

from flask import Blueprint, flash, redirect, render_template, request, url_for

from core import (
    ASSETS_DIR,
    CUSTOM_CSS,
    THEMES,
    load_config,
    mark_restart_needed,
    save_config,
)

bp = Blueprint("branding", __name__)

CSS_STARTER = """\
/* This stylesheet is injected into the Authelia login portal.
   Uncomment and adjust the examples below, then save. Changes apply
   immediately on the next page load - no restart needed. */

/* Page background */
/*
body, #root {
  background: #1c1c1e !important;
}
*/

/* Make all text easier to read */
/*
body {
  font-size: 105% !important;
}
*/

/* Primary buttons */
/*
button.MuiButton-containedPrimary {
  background-color: #03a9f4 !important;
}
*/
"""


@bp.route("/branding", methods=["GET", "POST"])
def index():
    config = load_config()
    if request.method == "POST":
        theme = request.form.get("theme", "light")
        if theme not in THEMES:
            flash("Invalid theme.", "error")
            return redirect(url_for("branding.index"))
        config["theme"] = theme
        config.setdefault("server", {})["asset_path"] = ASSETS_DIR
        save_config(config)

        os.makedirs(ASSETS_DIR, exist_ok=True)
        logo = request.files.get("logo")
        if logo and logo.filename:
            if not logo.filename.lower().endswith(".png"):
                flash("Logo must be a PNG file.", "error")
                return redirect(url_for("branding.index"))
            logo.save(os.path.join(ASSETS_DIR, "logo.png"))
        favicon = request.files.get("favicon")
        if favicon and favicon.filename:
            if not favicon.filename.lower().endswith(".ico"):
                flash("Favicon must be an ICO file.", "error")
                return redirect(url_for("branding.index"))
            favicon.save(os.path.join(ASSETS_DIR, "favicon.ico"))

        flash("Branding saved. Restart Authelia to apply.", "success")
        return redirect(url_for("branding.index"))

    try:
        with open(CUSTOM_CSS, encoding="utf-8") as fh:
            custom_css = fh.read()
    except FileNotFoundError:
        custom_css = ""
    return render_template(
        "branding.html",
        theme=config.get("theme", "light"),
        has_logo=os.path.exists(os.path.join(ASSETS_DIR, "logo.png")),
        has_favicon=os.path.exists(os.path.join(ASSETS_DIR, "favicon.ico")),
        custom_css=custom_css,
        css_starter=CSS_STARTER,
    )


@bp.route("/branding/css", methods=["POST"])
def custom_css():
    content = request.form.get("content", "")
    os.makedirs(ASSETS_DIR, exist_ok=True)
    if content.strip():
        with open(CUSTOM_CSS, "w", encoding="utf-8") as fh:
            fh.write(content)
        flash("Portal CSS saved. It applies on the next page load of the "
              "login portal - no restart needed.", "success")
    else:
        try:
            os.remove(CUSTOM_CSS)
        except FileNotFoundError:
            pass
        flash("Portal CSS removed.", "success")
    return redirect(url_for("branding.index"))


@bp.route("/branding/reset/<asset>", methods=["POST"])
def reset(asset):
    filename = {"logo": "logo.png", "favicon": "favicon.ico"}.get(asset)
    if not filename:
        flash("Unknown asset.", "error")
        return redirect(url_for("branding.index"))
    try:
        os.remove(os.path.join(ASSETS_DIR, filename))
        mark_restart_needed()
        flash(f"Custom {asset} removed. Restart Authelia to apply.",
              "success")
    except FileNotFoundError:
        flash(f"No custom {asset} to remove.", "error")
    return redirect(url_for("branding.index"))
