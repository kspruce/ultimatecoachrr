# Enhanced Clip Library System - Implementation Guide

## Overview

This upgrade adds powerful features to your Ultimate Frisbee clip library:

1. **Video-Level Tags**: Categorize footage type (game, training, scouting, etc.)
2. **Annotation Tags**: Detailed tactical tagging (offense, defense, skills, situations, etc.)
3. **User Tracking**: Track who created each annotation
4. **Enhanced Annotations**: Titles, key moments, visibility controls, player tagging
5. **Hierarchical Tag System**: Parent-child relationships for better organization

## New Features

### For Clips (Videos)
- Tag videos by type (Full Game, Training Session, Scouting, etc.)
- Track who uploaded each clip
- Mark clips as "featured"
- View count tracking
- Better organization with hierarchical tags

### For Annotations
- **Multi-user support**: See who added each annotation
- **Tag system**: Tag with offense, defense, skills, situations, outcomes, etc.
- **Key moments**: Flag important plays for quick reference
- **Visibility control**: Share with team, coaches only, or keep private
- **Player tagging**: Associate specific players with annotations
- **Titles**: Give annotations descriptive titles
- **Filtering**: Filter by event type, creator, tags, key moments

## Installation Steps

### 1. Update Your Models

**Update `app/models/clip.py`:**
Replace with the new `clip_model.py` file provided.

**Update `app/models/annotation.py`:**
Replace with the new `annotation.py` file provided.

**Update `app/models/__init__.py`:**
Add this import:
```python
from app.models.annotation import ClipAnnotation, AnnotationTag
```

### 2. Update Forms

Create or update `app/forms/annotation_forms.py`:
Use the `annotation_forms.py` file provided.

### 3. Add Tag Management

Add `tag_management.py` to your commands or utilities folder.

Then update your `commands.py` or create one if it doesn't exist:
```python
from tag_management import register_commands

def register_commands(app):
    from tag_management import register_commands as register_tag_commands
    register_tag_commands(app)
```

### 4. Database Migration

**Option A: Using Flask-Migrate (Recommended)**
```bash
# Create migration
flask db migrate -m "Add enhanced clip and annotation features"

# Review the migration file, then apply
flask db upgrade
```

**Option B: Manual Migration**
If you encounter issues, use the provided migration script:
```python
from migration_script import upgrade_database
upgrade_database()
```

### 5. Populate Default Tags

After migration, populate the tag system:
```bash
flask populate-tags
```

This creates:
- Video type tags (Full Game, Training Session, etc.)
- Annotation tags (Offense, Defense, Skills, Situations, etc.)

### 6. Update Your Routes

**In `app/routes/clip.py`**, add these new routes:

```python
from app.models.annotation import AnnotationTag
from app.forms.annotation_forms import AnnotationForm, AnnotationFilterForm
from flask_login import current_user

@bp.route('/clip/<int:clip_id>/annotation/add', methods=['GET', 'POST'])
@login_required
def add_annotation(clip_id):
    clip = Clip.query.get_or_404(clip_id)
    form = AnnotationForm()
    
    if form.validate_on_submit():
        annotation = ClipAnnotation(
            clip_id=clip_id,
            user_id=current_user.id,
            timestamp=form.timestamp.data,
            title=form.title.data,
            event_type=form.event_type.data,
            our_score=form.our_score.data,
            their_score=form.their_score.data,
            offense=form.offense.data,
            defense=form.defense.data,
            notes=form.notes.data,
            is_key_moment=form.is_key_moment.data,
            visibility=form.visibility.data,
            team_organization_id=current_user.team_organization_id
        )
        
        # Add tags
        selected_tags = AnnotationTag.query.filter(
            AnnotationTag.id.in_(form.tags.data)
        ).all()
        annotation.tags = selected_tags
        
        # Add players
        selected_players = Player.query.filter(
            Player.id.in_(form.players.data)
        ).all()
        annotation.players = selected_players
        
        db.session.add(annotation)
        db.session.commit()
        
        flash('Annotation added successfully!', 'success')
        return redirect(url_for('clip.view_clip', clip_id=clip_id))
    
    return render_template('clip/add_annotation.html', 
                         form=form, clip=clip)

@bp.route('/annotation/<int:annotation_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_annotation(annotation_id):
    annotation = ClipAnnotation.query.get_or_404(annotation_id)
    
    # Check permissions
    if not (current_user.id == annotation.user_id or 
            current_user.is_admin or current_user.is_coach):
        flash('You do not have permission to edit this annotation.', 'danger')
        return redirect(url_for('clip.view_clip', clip_id=annotation.clip_id))
    
    form = AnnotationForm(obj=annotation)
    
    if form.validate_on_submit():
        annotation.timestamp = form.timestamp.data
        annotation.title = form.title.data
        annotation.event_type = form.event_type.data
        annotation.our_score = form.our_score.data
        annotation.their_score = form.their_score.data
        annotation.offense = form.offense.data
        annotation.defense = form.defense.data
        annotation.notes = form.notes.data
        annotation.is_key_moment = form.is_key_moment.data
        annotation.visibility = form.visibility.data
        
        # Update tags
        selected_tags = AnnotationTag.query.filter(
            AnnotationTag.id.in_(form.tags.data)
        ).all()
        annotation.tags = selected_tags
        
        # Update players
        selected_players = Player.query.filter(
            Player.id.in_(form.players.data)
        ).all()
        annotation.players = selected_players
        
        db.session.commit()
        flash('Annotation updated successfully!', 'success')
        return redirect(url_for('clip.view_clip', clip_id=annotation.clip_id))
    
    # Pre-populate form
    form.tags.data = [tag.id for tag in annotation.tags]
    form.players.data = [player.id for player in annotation.players]
    
    return render_template('clip/edit_annotation.html', 
                         form=form, annotation=annotation)

@bp.route('/annotation/<int:annotation_id>/delete', methods=['POST'])
@login_required
def delete_annotation(annotation_id):
    annotation = ClipAnnotation.query.get_or_404(annotation_id)
    
    # Check permissions
    if not (current_user.id == annotation.user_id or 
            current_user.is_admin or current_user.is_coach):
        flash('You do not have permission to delete this annotation.', 'danger')
        return redirect(url_for('clip.view_clip', clip_id=annotation.clip_id))
    
    clip_id = annotation.clip_id
    db.session.delete(annotation)
    db.session.commit()
    
    flash('Annotation deleted successfully!', 'success')
    return redirect(url_for('clip.view_clip', clip_id=clip_id))
```

### 7. Update Templates

Replace `app/templates/clip/view_clip.html` with the new template provided.

### 8. Update Your Models Import

In your `app/__init__.py`, make sure these models are imported:
```python
from app.models import (
    # ... existing imports ...
    ClipAnnotation, AnnotationTag,  # Add these
)
```

## Usage Guide

### For Coaches/Admins

1. **Organize Video Library**:
   - Upload clips and tag them by type (game footage, training, scouting)
   - Mark important clips as "featured"
   - Associate clips with games and points

2. **Create Detailed Annotations**:
   - Add timestamps for key moments
   - Tag with tactical categories (offense, defense, skills)
   - Add notes and coaching points
   - Tag relevant players
   - Mark critical plays as "key moments"

3. **Manage Tags**:
   - Use hierarchical structure (e.g., Offense > Cutting > Under Cut)
   - Assign colors for visual organization
   - Activate/deactivate tags as needed

### For Players

1. **View Annotations**:
   - See who added each annotation
   - Filter by event type, player, or creator
   - Jump to specific timestamps
   - Focus on key moments

2. **Add Your Own**:
   - Contribute annotations during film sessions
   - Share insights with visibility controls
   - Tag yourself and teammates

## Tag Categories

### Video Tags (Clip-Level)
- Video Type / Context
  - Full Game
  - Training Session
  - Highlight / Tactic Showcase
  - Mixed Footage Compilation
  - Tournament / Competition Video

### Annotation Tags (Tactical)
- **Offense**: Handler movement, cutting, throws, set plays
- **Defense**: Person defense, zone, marks, turnovers
- **Skills**: Throwing skills, catching skills
- **Situations**: Pulling, sideline, wind, weather
- **Outcomes**: Hold, break, goal, assist, turnover
- **Field Zones**: Backfield, midfield, red zone, end zone
- **Personnel**: O-line, D-line, mixed line
- **Errors**: Drop, throwaway, miscommunication, violations
- **Tempo**: Fast break, slow play, timeouts
- **Opponent Scouting**: Opponent offense/defense/plays

## API Endpoints (Optional)

If you want to add API endpoints for mobile apps:

```python
@bp.route('/api/clip/<int:clip_id>/annotations')
def get_annotations_api(clip_id):
    annotations = ClipAnnotation.query.filter_by(clip_id=clip_id).all()
    return jsonify([{
        'id': a.id,
        'timestamp': a.timestamp,
        'title': a.title,
        'tags': [t.name for t in a.tags],
        'creator': a.created_by.username if a.created_by else None,
        'is_key_moment': a.is_key_moment
    } for a in annotations])
```

## Troubleshooting

### Tags Not Appearing
```bash
# Re-run tag population
flask populate-tags
```

### Migration Errors
```bash
# Reset migrations (backup your data first!)
flask db stamp head
flask db migrate -m "Recreate enhanced features"
flask db upgrade
```

### Foreign Key Errors
Make sure your database supports foreign keys. For SQLite:
```python
# In your config
SQLALCHEMY_ENGINE_OPTIONS = {
    "connect_args": {"check_same_thread": False},
    "pool_pre_ping": True,
}
```

## Future Enhancements

Consider adding:
1. **Drawing tools**: Annotate with arrows and shapes on video frames
2. **Playlists**: Create collections of related annotations
3. **Export**: Export annotations to PDF or video overlays
4. **Statistics**: Aggregate stats from annotations
5. **AI suggestions**: Auto-tag clips based on content
6. **Collaborative annotations**: Multiple users annotating same timestamp

## Support

For issues or questions:
1. Check the Flask logs for errors
2. Verify database migrations completed successfully
3. Ensure all model relationships are properly defined
4. Test with a small dataset first

## Credits

This enhanced system builds on your existing clip library with:
- Hierarchical tag system inspired by video analysis platforms
- Multi-user annotations for collaborative learning
- Tactical categorization specific to Ultimate Frisbee

---

**Version**: 2.0  
**Last Updated**: 2025  
**Compatibility**: Flask 2.x, SQLAlchemy 1.4+
