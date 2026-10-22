"""Clip library: clips, their annotations, tags, and sharing/exports."""
from flask import Blueprint

from app.utils.clip_video import format_timestamp

bp = Blueprint('clip', __name__, url_prefix='/clips')
bp.add_app_template_filter(format_timestamp, 'clip_time')

from app.routes.clip import annotations, clips, sharing, tags  # noqa: E402,F401
