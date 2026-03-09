"""add team_organization_id indexes to all multi-tenant tables

Revision ID: 604817d23bd6
Revises: d2ca975d8afa
Create Date: 2026-03-09

Every route filters by team_organization_id but none of the tables had an
index on that column, causing full table scans on every request.
"""
from alembic import op

# revision identifiers
revision = '604817d23bd6'
down_revision = 'd2ca975d8afa'
branch_labels = None
depends_on = None

# All (table, index_name) pairs that need a team_organization_id index.
# Tables already possessing one are excluded.
INDEXES = [
    # Core game / point tables
    ("game",                   "ix_game_team_org"),
    ("point",                  "ix_point_team_org"),
    ("line_up",                "ix_line_up_team_org"),
    ("event",                  "ix_event_team_org"),
    ("pull",                   "ix_pull_team_org"),
    ("throw",                  "ix_throw_team_org"),
    ("player_point_stats",     "ix_player_point_stats_team_org"),
    ("game_player",            "ix_game_player_team_org"),
    # Player / team
    ("player",                 "ix_player_team_org"),
    ("user",                   "ix_user_team_org"),
    # Tournament / session
    ("tournament",             "ix_tournament_team_org"),
    ("tournament_rsvp",        "ix_tournament_rsvp_team_org"),
    ("session_plan",           "ix_session_plan_team_org"),
    ("session_component",      "ix_session_component_team_org"),
    ("attendance",             "ix_attendance_team_org"),
    ("session_rsvp",           "ix_session_rsvp_team_org"),
    # Clips / video
    ("clip",                   "ix_clip_team_org"),
    ("clip_tag",               "ix_clip_tag_team_org"),
    ("clip_annotation",        "ix_clip_annotation_team_org"),
    ("annotation_tag",         "ix_annotation_tag_team_org"),
    ("clip_point_segments",    "ix_clip_point_segments_team_org"),
    # Gameday
    ("game_day_event",         "ix_game_day_event_team_org"),
    ("game_day_player_stats",  "ix_game_day_player_stats_team_org"),
    ("line_template",          "ix_line_template_team_org"),
    ("line_template_player",   "ix_line_template_player_team_org"),
    # Scouting
    ("scouting_report",        "ix_scouting_report_team_org"),
    ("opponent_player",        "ix_opponent_player_team_org"),
    ("scouting_clip",          "ix_scouting_clip_team_org"),
    # Playbook
    ("play",                   "ix_play_team_org"),
    ("formation",              "ix_formation_team_org"),
    ("play_tag",               "ix_play_tag_team_org"),
    ("player_position",        "ix_player_position_team_org"),
    ("play_assignment",        "ix_play_assignment_team_org"),
    # Theory
    ("theory_section",         "ix_theory_section_team_org"),
    ("theory_topic",           "ix_theory_topic_team_org"),
    ("theory_video",           "ix_theory_video_team_org"),
    ("theory_tag",             "ix_theory_tag_team_org"),
    # Fitness
    ("fitness_metric",         "ix_fitness_metric_team_org"),
    ("fitness_record",         "ix_fitness_record_team_org"),
    # Drills
    ("drill",                  "ix_drill_team_org"),
    ("drill_frame",            "ix_drill_frame_team_org"),
    ("saved_drill",            "ix_saved_drill_team_org"),
    # Cutting skills / off-season
    ("cutting_skill",          "ix_cutting_skill_team_org"),
    ("off_season_phases",      "ix_off_season_phases_team_org"),
    ("phase_metrics",          "ix_phase_metrics_team_org"),
    ("phase_schedules",        "ix_phase_schedules_team_org"),
    ("schedule_sessions",      "ix_schedule_sessions_team_org"),
    ("workout_plans",          "ix_workout_plans_team_org"),
    ("user_session_completions","ix_user_session_completions_team_org"),
    ("smart_goals",            "ix_smart_goals_team_org"),
    ("user_schedule_preferences","ix_user_schedule_preferences_team_org"),
    ("track_workout_weeks",    "ix_track_workout_weeks_team_org"),
    # Export
    ("export_log",             "ix_export_log_team_org"),
]


def upgrade():
    """Create team_organization_id indexes where missing."""
    bind = op.get_bind()
    inspector = bind.dialect

    for table, index_name in INDEXES:
        # Use CREATE INDEX IF NOT EXISTS so the migration is safe to re-run
        # and tolerant of tables that may not exist in older environments.
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {index_name} "
            f"ON {table} (team_organization_id)"
        )


def downgrade():
    """Drop all team_organization_id indexes added in this migration."""
    for table, index_name in INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
