# app/commands.py
import os
import click
from flask.cli import with_appcontext
from app import db
from app.models.user import User
from app.utils.data_manager import DataManager
from app.utils.tag_management import register_commands as register_tag_commands
import json

@click.command('create-admin')
@click.option('--email', default=lambda: os.environ.get('ADMIN_EMAIL', ''), prompt='Admin email', help='Admin user email address')
@click.option('--username', default='admin', prompt='Admin username', help='Admin username')
@click.password_option(help='Admin password')
@with_appcontext
def create_admin(email, username, password):
    """Create an admin user (reads ADMIN_EMAIL from env if set)"""
    if not email:
        raise click.UsageError('Email is required. Pass --email or set ADMIN_EMAIL env var.')

    existing = User.query.filter_by(email=email).first()
    if existing:
        click.echo(f'A user with email {email} already exists.')
        return

    admin = User(
        username=username,
        email=email,
        role='admin',
        is_admin=True
    )
    admin.set_password(password)

    db.session.add(admin)
    db.session.commit()

    click.echo(f'Admin user "{username}" ({email}) created successfully.')

@click.command()
@click.option('--output-dir', default='data_exports', help='Directory to save exported data')
@click.option('--timestamp/--no-timestamp', default=True, help='Include timestamp in directory name')
@with_appcontext
def export_data(output_dir, timestamp):
    """Export all model data to JSON files."""
    click.echo("Starting data export...")
    
    manager = DataManager(export_dir=output_dir)
    
    try:
        export_path = manager.export_all_data(timestamp=timestamp)
        click.echo("✅ Data export completed successfully!")
        click.echo(f"📁 Export location: {export_path}")
        
        # Show summary
        summary_path = f"{export_path}/export_summary.json"
        with open(summary_path, 'r') as f:
            summary = json.load(f)
        
        click.echo("\n📊 Export Summary:")
        total_records = 0
        for table_name, info in summary.items():
            if isinstance(info, dict) and 'records_exported' in info:
                records = info['records_exported']
                total_records += records
                status = "✅" if records > 0 else "⚠️"
                click.echo(f"  {status} {table_name}: {records} records")
        
        click.echo(f"\n📈 Total records exported: {total_records}")
        
    except Exception as e:
        click.echo(f"❌ Export failed: {e}")
        raise

@click.command()
@click.option('--import-dir', required=True, help='Directory containing exported data')
@click.option('--clear/--no-clear', default=False, help='Clear existing data before import')
@click.confirmation_option(prompt='Are you sure you want to import data? This may modify your database.')
@with_appcontext
def import_data(import_dir, clear):
    """Import data from JSON files into models."""
    click.echo("Starting data import...")
    
    if clear:
        click.echo("⚠️  WARNING: Existing data will be cleared!")
    
    manager = DataManager()
    
    try:
        summary = manager.import_all_data(import_dir, clear_existing=clear)
        
        if summary['status'] == 'completed':
            click.echo("✅ Data import completed successfully!")
        else:
            click.echo(f"❌ Import failed: {summary.get('error', 'Unknown error')}")
            return
        
        # Show summary
        click.echo("\n📊 Import Summary:")
        total_records = 0
        for table_name, info in summary['results'].items():
            if isinstance(info, dict) and 'records_imported' in info:
                records = info['records_imported']
                total_records += records
                status = "✅" if records > 0 else "⚠️"
                click.echo(f"  {status} {table_name}: {records} records")
                
                if 'errors' in info:
                    click.echo(f"    ⚠️  {len(info['errors'])} errors occurred")
        
        click.echo(f"\n📈 Total records imported: {total_records}")
        
    except Exception as e:
        click.echo(f"❌ Import failed: {e}")
        raise

@click.command()
@with_appcontext
def show_models():
    """Show information about discovered models."""
    manager = DataManager()
    info = manager.get_model_info()
    
    click.echo(f"📋 Discovered {info['total_models']} models:")
    click.echo(f"🔄 Processing order: {' → '.join(info['dependency_order'])}")
    
    click.echo("\n📊 Model Details:")
    for table_name, model_info in info['models'].items():
        click.echo(f"\n  📄 {table_name} ({model_info['class_name']})")
        click.echo(f"     Records: {model_info['record_count']}")
        click.echo(f"     Columns: {len(model_info['columns'])}")
        
        if model_info['foreign_keys']:
            click.echo("     Foreign Keys:")
            for fk in model_info['foreign_keys']:
                click.echo(f"       • {fk['column']} → {fk['references']}")

# Register commands with Flask CLI
@click.command('import-season')
@click.argument('season_file', type=click.Path(exists=True, dir_okay=False))
@click.option('--images-dir', type=click.Path(exists=True, file_okay=False),
              help='Folder the diagram "file"/"svg" paths are relative to')
@click.option('--team-org', 'team_org_id', type=int, required=True,
              help='TeamOrganization id to import into')
@click.option('--dry-run', is_flag=True, help='Validate and report, but write nothing')
@with_appcontext
def import_season_command(season_file, images_dir, team_org_id, dry_run):
    """Import a season of session plans and drills (herd-session-v1 JSON)."""
    from app.utils.season_import import import_season, load_season_file, SeasonImportError

    try:
        data = load_season_file(season_file)
    except json.JSONDecodeError as e:
        raise click.ClickException(f'{season_file} is not valid JSON: {e}')

    try:
        summary = import_season(data, images_dir, team_org_id, dry_run=dry_run)
    except SeasonImportError as e:
        click.echo(f'Import failed, nothing was written ({len(e.errors)} problems):', err=True)
        for error in e.errors:
            click.echo(f'  - {error}', err=True)
        raise SystemExit(1)

    click.echo(summary.report())


@click.command('import-season-plan')
@click.argument('folder', type=click.Path(exists=True, file_okay=False))
@click.option('--team', 'team_slug', required=True, help='Slug of the team to import into')
@click.option('--season', help='Season label (e.g. 2027/28); read from the manifest if not given')
@click.option('--dry-run', is_flag=True, help='Parse and report, but write nothing')
@click.option('--replace', is_flag=True, help='Wipe the existing plan for this season and import it fresh')
@click.option('--build-sessions', is_flag=True,
              help='Build sessions from the weekly session notes (after the first build, '
                   'every import updates them anyway)')
@with_appcontext
def import_season_plan_command(folder, team_slug, season, dry_run, replace, build_sessions):
    """Import a season plan (manifest.json plus markdown tabs) into a team.

    Re-running updates the same plan (matched on team and season). The
    team's Season plan feature is left as it is; switch it on in team
    settings.
    """
    from app.models.team_organization import TeamOrganization
    from app.utils.season_plan_import import import_season_plan, SeasonPlanImportError

    team = TeamOrganization.query.filter_by(slug=team_slug).first()
    if team is None:
        raise click.ClickException(f'No team with slug {team_slug!r}')

    try:
        report = import_season_plan(folder, team, season=season, dry_run=dry_run, replace=replace,
                                    build_sessions=build_sessions or None)
    except SeasonPlanImportError as e:
        click.echo(f'Import failed, nothing was written ({len(e.errors)} problems):', err=True)
        for error in e.errors:
            click.echo(f'  - {error}', err=True)
        raise SystemExit(1)

    click.echo(f'{team.name} ({team.slug})')
    click.echo(report.text())
    settings = team.settings
    if not dry_run and not (settings and settings.season_plan_enabled):
        click.echo('The Season plan feature is off for this team: switch it on in Team settings > Features.')


@click.command('import-handbook')
@click.argument('path', type=click.Path(exists=True, dir_okay=False))
@click.option('--team', 'team_slug', required=True, help='Slug of the team to import into')
@click.option('--dry-run', is_flag=True, help='Parse and report, but write nothing')
@click.option('--replace', is_flag=True, help='Overwrite pages already on the site with the file\'s wording')
@with_appcontext
def import_handbook_command(path, team_slug, dry_run, replace):
    """Load the leadership handbook (imports/leadership-handbook/handbook.html)
    into a team.

    Re-running adds new pages and reorders, but leaves pages already on the
    site as leaders edited them unless --replace is given. The team's
    Leadership handbook feature is left as it is; switch it on in team
    settings.
    """
    from app.models.team_organization import TeamOrganization
    from app.utils.handbook import import_handbook, HandbookImportError

    team = TeamOrganization.query.filter_by(slug=team_slug).first()
    if team is None:
        raise click.ClickException(f'No team with slug {team_slug!r}')

    try:
        report = import_handbook(path, team, dry_run=dry_run, replace=replace)
    except HandbookImportError as e:
        click.echo(f'Import failed, nothing was written ({len(e.errors)} problems):', err=True)
        for error in e.errors:
            click.echo(f'  - {error}', err=True)
        raise SystemExit(1)

    click.echo(f'{team.name} ({team.slug})')
    click.echo(report.text())
    settings = team.settings
    if not dry_run and not (settings and settings.leadership_handbook_enabled):
        click.echo('The Leadership handbook feature is off for this team: switch it on in Team settings > Features.')


@click.command('import-programme')
@click.argument('folder', type=click.Path(exists=True, file_okay=False))
@click.option('--team', 'team_slug', required=True, help='Slug of the team to import into')
@click.option('--name', required=True, help='Name of the new programme')
@click.option('--start', 'start_date', help='Start date (YYYY-MM-DD) for a calendar programme')
@click.option('--template', 'as_template', is_flag=True, help='Import as a reusable template')
@click.option('--dry-run', is_flag=True, help='Check and report, but write nothing')
@with_appcontext
def import_programme_command(folder, team_slug, name, start_date, as_template, dry_run):
    """Import a training programme from programme.csv (and tests.csv, if
    present) in FOLDER, the same format as Programmes > Import on the site
    (docs/PROGRAMME_IMPORT.md). It arrives as a draft for a coach to check
    and publish. The same files are never imported twice into one team."""
    from datetime import date
    from app.models.team_organization import TeamOrganization
    from app.utils import programme_import as pimport

    team = TeamOrganization.query.filter_by(slug=team_slug).first()
    if team is None:
        raise click.ClickException(f'No team with slug {team_slug!r}')
    with open(os.path.join(folder, 'programme.csv'), encoding='utf-8-sig') as f:
        programme_rows = pimport.rows_from_csv(f.read())
    tests_path = os.path.join(folder, 'tests.csv')
    test_rows = []
    if os.path.exists(tests_path):
        with open(tests_path, encoding='utf-8-sig') as f:
            test_rows = pimport.rows_from_csv(f.read())
    parsed = pimport.parse(programme_rows, test_rows)
    for row, msg in parsed['warnings']:
        click.echo(f'  warning, row {row}: {msg}')
    if parsed['errors']:
        for row, msg in parsed['errors']:
            click.echo(f'  error, row {row}: {msg}', err=True)
        raise SystemExit(1)
    click.echo(', '.join(f'{v} {k}' for k, v in parsed['counts'].items()))
    digest = pimport.content_hash(programme_rows, test_rows)
    existing = pimport.find_duplicate(team.id, digest)
    if existing:
        raise click.ClickException(f'Already imported into {team.name} as "{existing.name}" (id {existing.id}).')
    if dry_run:
        click.echo('Dry run: nothing written.')
        return
    programme = pimport.build(parsed, team.id, None, name=name,
                              start_date=date.fromisoformat(start_date) if start_date else None,
                              kind='template' if as_template else 'programme',
                              filename=os.path.basename(os.path.normpath(folder)), digest=digest)
    db.session.commit()
    click.echo(f'Imported "{programme.name}" into {team.name} as a draft (id {programme.id}). '
               'A coach can check it under Training > Programmes and publish it.')


@click.command('reset-two-factor')
@click.argument('username')
@with_appcontext
def reset_two_factor(username):
    """Turn off two-step sign-in for someone who lost their phone and their
    recovery codes. A superadmin is asked to set it up again at next login."""
    from app.utils import two_factor
    user = User.query.filter_by(username=username).first()
    if user is None:
        raise click.UsageError(f'No user called {username}.')
    two_factor.disable(user)
    db.session.commit()
    click.echo(f'Two-step sign-in is off for {username}; they can log in with their password.')


@click.command('backfill-seasons')
@with_appcontext
def backfill_seasons():
    """Set up seasons for every team that has none yet (safe to run again)."""
    from app.models.team_organization import TeamOrganization
    from app.utils.season import ensure_seasons

    for team in TeamOrganization.query.order_by(TeamOrganization.id):
        made = ensure_seasons(team.id)
        click.echo(f'{team.name}: {"seasons set up" if made else "already has seasons"}')


@click.command('training-jobs')
@with_appcontext
def training_jobs_command():
    """Make training schedules' next dates, send due reminders and weekly
    Discord posts (what the web process does on its own every hour)."""
    from flask import current_app
    from app.scheduler import run_jobs
    result = run_jobs(current_app._get_current_object())
    click.echo(', '.join(f'{k}: {v}' for k, v in result.items()))


def register_commands(app):
    """Register custom commands with the Flask app."""
    app.cli.add_command(training_jobs_command)
    app.cli.add_command(export_data)
    app.cli.add_command(import_season_command)
    app.cli.add_command(import_season_plan_command)
    app.cli.add_command(import_handbook_command)
    app.cli.add_command(import_programme_command)
    app.cli.add_command(import_data)
    app.cli.add_command(show_models)
    app.cli.add_command(reset_two_factor)
    app.cli.add_command(backfill_seasons)
    register_tag_commands(app)
