"""Clip library: clips, their annotations, tags, and sharing/exports."""
from flask import Blueprint

bp = Blueprint('clip', __name__, url_prefix='/clips')

from app.routes.clip import annotations, clips, sharing, tags  # noqa: E402,F401
