"""
app/routes/pages.py — Serve frontend HTML pages
All page routes serve from app/templates/
Static assets served by NGINX in production.
"""
from flask import Blueprint, render_template, send_from_directory
import os

pages_bp = Blueprint("pages", __name__)


@pages_bp.get("/")
def index():
    return render_template("index.html")

@pages_bp.get("/login")
def login():
    return render_template("login.html")

@pages_bp.get("/register")
def register():
    return render_template("register.html")

@pages_bp.get("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@pages_bp.get("/suggest")
def suggest():
    return render_template("suggest.html")

@pages_bp.get("/manifest.json")
def manifest():
    return send_from_directory(
        os.path.join(pages_bp.root_path, "..", "static"),
        "manifest.json"
    )

@pages_bp.get("/sw.js")
def service_worker():
    return send_from_directory(
        os.path.join(pages_bp.root_path, "..", "static"),
        "sw.js",
        mimetype="application/javascript"
    )
