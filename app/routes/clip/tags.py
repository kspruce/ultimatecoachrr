"""Clip tags and annotation tags."""

from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required

from app import db
from app.forms.clip import ClipTagForm
from app.models import ClipTag
from app.models.annotation import AnnotationTag
from app.routes.clip import bp
from app.utils.team_filter import get_current_team_id
from app.utils.utils import admin_required


@bp.route('/tags')
@login_required
@admin_required
def tags():
    """View all clip tags with statistics"""
    team_id = get_current_team_id()
    
    # Get tags with clip counts
    from sqlalchemy import func
    from app.models.clip import clip_tag_relation
    
    tags_query = db.session.query(
        ClipTag,
        func.count(clip_tag_relation.c.clip_id).label('clip_count')
    ).outerjoin(
        clip_tag_relation, ClipTag.id == clip_tag_relation.c.tag_id
    ).filter(
        ClipTag.team_organization_id == team_id
    ).group_by(
        ClipTag.id
    ).order_by(
        ClipTag.category,
        ClipTag.name
    )
    
    tags_with_counts = tags_query.all()
    
    # Group by category for display
    tags_by_category = {}
    for tag, count in tags_with_counts:
        category = tag.category or 'Uncategorized'
        if category not in tags_by_category:
            tags_by_category[category] = []
        tags_by_category[category].append((tag, count))
    
    return render_template('clip/tags.html', 
                         tags_by_category=tags_by_category)


@bp.route('/tags/bulk_create', methods=['GET', 'POST'])
@login_required
@admin_required
def bulk_create_tags():
    """Bulk create common tags for video organization"""
    team_id = get_current_team_id()
    
    if request.method == 'POST':
        # Define common tag structure
        common_tags = {
            'Video Type': [
                ('Full Game', '#1976D2'),
                ('Highlight Reel', '#FFA000'),
                ('Training Session', '#388E3C'),
                ('Drill Demonstration', '#7B1FA2'),
                ('Team Meeting', '#0097A7'),
                ('Individual Footage', '#5D4037')
            ],
            'Game Context': [
                ('Tournament Game', '#D32F2F'),
                ('League Game', '#C2185B'),
                ('Scrimmage', '#7B1FA2'),
                ('Championship', '#FFD700'),
                ('Qualifier', '#512DA8')
            ],
            'Training Type': [
                ('Offensive Practice', '#1976D2'),
                ('Defensive Practice', '#D32F2F'),
                ('Conditioning', '#388E3C'),
                ('Skills Training', '#FFA000'),
                ('Strategy Session', '#5D4037'),
                ('Film Review', '#0097A7')
            ],
            'Skill Focus': [
                ('Throwing', '#1976D2'),
                ('Cutting', '#388E3C'),
                ('Marking', '#D32F2F'),
                ('Handler Movement', '#7B1FA2'),
                ('Positioning', '#FFA000'),
                ('Communication', '#0097A7')
            ],
            'Strategic Focus': [
                ('Offensive Sets', '#1976D2'),
                ('Defensive Sets', '#D32F2F'),
                ('Zone Offense', '#388E3C'),
                ('Zone Defense', '#C2185B'),
                ('Transition', '#FFA000'),
                ('Endzone Plays', '#7B1FA2')
            ],
            'Player Development': [
                ('Rookie Training', '#4CAF50'),
                ('Advanced Skills', '#FF5722'),
                ('Captain Development', '#FFD700'),
                ('Position-Specific', '#3F51B5'),
                ('Fitness', '#8BC34A')
            ],
            'Analysis': [
                ('Good Example', '#4CAF50'),
                ('Learning Opportunity', '#FFA000'),
                ('Key Moment', '#FFD700'),
                ('Tactical Breakdown', '#3F51B5'),
                ('Common Mistake', '#F44336')
            ]
        }
        
        created_count = 0
        skipped_count = 0
        
        for category, tags in common_tags.items():
            for tag_name, color in tags:
                # Check if tag already exists
                existing = ClipTag.query.filter_by(
                    name=tag_name,
                    team_organization_id=team_id
                ).first()
                
                if not existing:
                    new_tag = ClipTag(
                        name=tag_name,
                        category=category,
                        color=color,
                        team_organization_id=team_id,
                        is_active=True
                    )
                    db.session.add(new_tag)
                    created_count += 1
                else:
                    skipped_count += 1
        
        db.session.commit()
        
        flash(f'Created {created_count} new tags. Skipped {skipped_count} existing tags.', 'success')
        return redirect(url_for('clip.tags'))
    
    return render_template('clip/bulk_create_tags.html')


@bp.route('/tags/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_tag():
    """Add a new clip tag"""
    team_id = get_current_team_id()
    form = ClipTagForm()

    if form.validate_on_submit():
        # Check if tag already exists in this team (by name)
        existing_tag = ClipTag.query.filter_by(
            name=form.name.data,
            team_organization_id=team_id
        ).first()

        if existing_tag:
            flash(f'Tag "{form.name.data}" already exists!', 'danger')
            return render_template('clip/tag_form.html', form=form, title='Add Tag')

        # Resolve parent tag (optional, 0 means None)
        parent_id = form.parent_tag_id.data if hasattr(form, 'parent_tag_id') else 0
        if parent_id and parent_id > 0:
            parent = ClipTag.query.filter_by(id=parent_id, team_organization_id=team_id).first()
            parent_tag_id = parent.id if parent else None
        else:
            parent_tag_id = None

        tag = ClipTag(
            name=form.name.data,
            category=form.category.data if hasattr(form, 'category') else None,
            color=form.color.data if hasattr(form, 'color') else None,
            description=form.description.data if hasattr(form, 'description') else None,
            is_active=form.is_active.data if hasattr(form, 'is_active') else True,
            parent_tag_id=parent_tag_id,
            team_organization_id=team_id
        )
        db.session.add(tag)
        db.session.commit()

        flash(f'Tag "{tag.name}" has been added!', 'success')
        return redirect(url_for('clip.tags'))

    return render_template('clip/tag_form.html', form=form, title='Add Tag')


@bp.route('/tags/edit/<int:tag_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_tag(tag_id):
    # Get current team ID
    team_id = get_current_team_id()

    # Filter tag by team
    tag = ClipTag.query.filter_by(id=tag_id, team_organization_id=team_id).first_or_404()

    form = ClipTagForm(obj=tag)

    if form.validate_on_submit():
        # Check if tag already exists in this team (same name, different id)
        existing_tag = ClipTag.query.filter(
            ClipTag.name == form.name.data,
            ClipTag.id != tag_id,
            ClipTag.team_organization_id == team_id
        ).first()

        if existing_tag:
            flash(f'Tag "{form.name.data}" already exists!', 'danger')
            return render_template('clip/tag_form.html', form=form, title='Edit Tag')

        # Resolve and validate parent tag (optional)
        parent_tag_id = None
        if hasattr(form, 'parent_tag_id'):
            raw_parent_id = form.parent_tag_id.data
            if raw_parent_id and raw_parent_id > 0:
                # Cannot set itself as parent
                if raw_parent_id == tag_id:
                    flash('A tag cannot be its own parent.', 'danger')
                    return render_template('clip/tag_form.html', form=form, tag=tag, title='Edit Tag')

                potential_parent = ClipTag.query.filter_by(
                    id=raw_parent_id, team_organization_id=team_id
                ).first()

                if not potential_parent:
                    flash('Selected parent tag was not found in your team.', 'danger')
                    return render_template('clip/tag_form.html', form=form, tag=tag, title='Edit Tag')

                # Check for circular parent relationship by walking up ancestors
                current_check = potential_parent
                while current_check:
                    if current_check.id == tag_id:
                        flash('Cannot set parent tag: This would create a circular relationship!', 'danger')
                        return render_template('clip/tag_form.html', form=form, tag=tag, title='Edit Tag')
                    current_check = getattr(current_check, 'parent', None)

                parent_tag_id = potential_parent.id

        # Persist fields
        tag.name = form.name.data
        if hasattr(form, 'category'):
            tag.category = form.category.data
        if hasattr(form, 'color'):
            tag.color = form.color.data
        if hasattr(form, 'description'):
            tag.description = form.description.data
        if hasattr(form, 'is_active'):
            tag.is_active = form.is_active.data
        if hasattr(form, 'parent_tag_id'):
            tag.parent_tag_id = parent_tag_id

        db.session.commit()

        flash(f'Tag "{tag.name}" has been updated!', 'success')
        return redirect(url_for('clip.tags'))

    return render_template('clip/tag_form.html', form=form, tag=tag, title='Edit Tag')


@bp.route('/tags/delete/<int:tag_id>', methods=['POST'])
@login_required
@admin_required
def delete_tag(tag_id):
    # Get current team ID
    team_id = get_current_team_id()
    
    # Filter tag by team
    tag = ClipTag.query.filter_by(id=tag_id, team_organization_id=team_id).first_or_404()
    
    name = tag.name
    
    # Clear relationships
    for clip in tag.clips:
        clip.tags.remove(tag)
    
    db.session.delete(tag)
    db.session.commit()
    
    flash(f'Tag "{name}" has been deleted!', 'success')
    return redirect(url_for('clip.tags'))


@bp.route('/annotation-tags')
@login_required
@admin_required
def annotation_tags():
    """View all annotation tags"""
    team_id = get_current_team_id()
    tags = AnnotationTag.query.filter_by(team_organization_id=team_id).order_by(
        AnnotationTag.category, AnnotationTag.name
    ).all()
    return render_template('clip/annotation_tags.html', tags=tags)


@bp.route('/annotation-tags/bulk_create', methods=['GET', 'POST'])
@login_required
@admin_required
def bulk_create_annotation_tags():
    """Bulk create common annotation tags for video analysis"""
    team_id = get_current_team_id()

    # Define common annotation tag structure
    # Each top-level key is a category; we create a parent tag with the same name,
    # then create child tags under it. Colors are just reasonable defaults.
    common = {
        'Offense': {
            'color': '#1976D2',
            'children': [
                ('Handler Movement', '#1565C0'),
                ('Reset', '#1E88E5'),
                ('Break Side', '#42A5F5'),
                ('Deep Shot', '#64B5F6'),
                ('Give-and-Go', '#90CAF9'),
                ('Endzone Offense', '#0D47A1'),
            ]
        },
        'Defense': {
            'color': '#D32F2F',
            'children': [
                ('Force Flick', '#C62828'),
                ('Force Backhand', '#B71C1C'),
                ('No Around', '#EF5350'),
                ('Poach', '#E53935'),
                ('Help Defense', '#F44336'),
                ('Zone Defense', '#8E24AA'),
            ]
        },
        'Throws': {
            'color': '#388E3C',
            'children': [
                ('Backhand', '#2E7D32'),
                ('Forehand', '#43A047'),
                ('Hammer', '#66BB6A'),
                ('Scoober', '#81C784'),
                ('High Release', '#A5D6A7'),
                ('Inside', '#4CAF50'),
                ('Around', '#66BB6A'),
            ]
        },
        'Cuts': {
            'color': '#FFA000',
            'children': [
                ('Under', '#FB8C00'),
                ('Deep', '#F57C00'),
                ('Break', '#FFB300'),
                ('Continuation', '#FFCA28'),
                ('Upline', '#FF9800'),
            ]
        },
        'Turnovers': {
            'color': '#5D4037',
            'children': [
                ('Throwaway', '#6D4C41'),
                ('Drop', '#8D6E63'),
                ('Block', '#4E342E'),
                ('Stall Out', '#795548'),
                ('Misc Penalty', '#A1887F'),
            ]
        },
        'Outcomes': {
            'color': '#0097A7',
            'children': [
                ('Goal', '#00838F'),
                ('Assist', '#00ACC1'),
                ('Hockey Assist', '#26C6DA'),
                ('Break Point', '#00BCD4'),
                ('Hold', '#4DD0E1'),
            ]
        },
        'Review': {
            'color': '#7B1FA2',
            'children': [
                ('Good Example', '#6A1B9A'),
                ('Learning Opportunity', '#8E24AA'),
                ('Key Moment', '#AB47BC'),
                ('Tactical Breakdown', '#BA68C8'),
                ('Common Mistake', '#CE93D8'),
            ]
        }
    }

    if request.method == 'POST':
        created_count = 0
        skipped_count = 0

        def get_or_create_parent(name, category, color):
            existing = AnnotationTag.query.filter_by(
                name=name, team_organization_id=team_id
            ).first()
            if existing:
                return existing, False
            obj = AnnotationTag(
                name=name,
                category=category,
                parent_tag_id=None,
                color=color,
                description=None,
                is_active=True,
                team_organization_id=team_id
            )
            db.session.add(obj)
            return obj, True

        def get_or_create_child(name, category, color, parent_id):
            existing = AnnotationTag.query.filter_by(
                name=name, team_organization_id=team_id
            ).first()
            if existing:
                return existing, False
            obj = AnnotationTag(
                name=name,
                category=category,
                parent_tag_id=parent_id,
                color=color,
                description=None,
                is_active=True,
                team_organization_id=team_id
            )
            db.session.add(obj)
            return obj, True

        # Create parents and children
        for category, conf in common.items():
            parent, parent_created = get_or_create_parent(category, category, conf['color'])
            created_count += 1 if parent_created else 0
            skipped_count += 0 if parent_created else 1

            for child_name, child_color in conf['children']:
                _, child_created = get_or_create_child(child_name, category, child_color, parent.id)
                created_count += 1 if child_created else 0
                skipped_count += 0 if child_created else 1

        db.session.commit()

        flash(f'Created {created_count} annotation tags. Skipped {skipped_count} existing.', 'success')
        return redirect(url_for('clip.annotation_tags'))

    # GET => show preview page
    return render_template('clip/bulk_create_annotation_tags.html', common=common)


@bp.route('/annotation-tags/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_annotation_tag():
    """Add a new annotation tag"""
    from app.forms.annotation import AnnotationTagForm
    team_id = get_current_team_id()
    form = AnnotationTagForm()
    
    # Filter parent tag choices to only show tags from current team
    form.parent_tag_id.choices = [(0, 'None (Root Tag)')] + [
        (t.id, t.full_path) for t in AnnotationTag.query.filter_by(
            team_organization_id=team_id,
            is_active=True
        ).order_by(AnnotationTag.name).all()
    ]
    
    if form.validate_on_submit():
        # Check if tag already exists in this team
        existing_tag = AnnotationTag.query.filter_by(
            name=form.name.data,
            team_organization_id=team_id
        ).first()
        
        if existing_tag:
            flash(f'Annotation tag "{form.name.data}" already exists!', 'danger')
            return render_template('clip/annotation_tag_form.html', form=form, title='Add Annotation Tag')
        
        tag = AnnotationTag(
            name=form.name.data,
            category=form.category.data,
            parent_tag_id=form.parent_tag_id.data if form.parent_tag_id.data > 0 else None,
            color=form.color.data,
            description=form.description.data,
            is_active=form.is_active.data,
            team_organization_id=team_id
        )
        db.session.add(tag)
        db.session.commit()
        
        flash(f'Annotation tag "{tag.name}" has been added!', 'success')
        return redirect(url_for('clip.annotation_tags'))
    
    return render_template('clip/annotation_tag_form.html', form=form, title='Add Annotation Tag')


@bp.route('/annotation-tags/edit/<int:tag_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_annotation_tag(tag_id):
    """Edit an annotation tag"""
    from app.forms.annotation import AnnotationTagForm
    team_id = get_current_team_id()
    tag = AnnotationTag.query.filter_by(id=tag_id, team_organization_id=team_id).first_or_404()
    
    form = AnnotationTagForm(obj=tag)
    
    # Filter parent tag choices to only show tags from current team (excluding self)
    form.parent_tag_id.choices = [(0, 'None (Root Tag)')] + [
        (t.id, t.full_path) for t in AnnotationTag.query.filter(
            AnnotationTag.team_organization_id == team_id,
            AnnotationTag.is_active == True,
            AnnotationTag.id != tag_id  # Don't allow tag to be its own parent
        ).order_by(AnnotationTag.name).all()
    ]
    
    if request.method == 'GET':
        # Pre-populate form with existing data
        if tag.parent_tag_id:
            form.parent_tag_id.data = tag.parent_tag_id
        else:
            form.parent_tag_id.data = 0
    
    if form.validate_on_submit():
        # Check if tag name already exists in this team (excluding current tag)
        existing_tag = AnnotationTag.query.filter(
            AnnotationTag.name == form.name.data,
            AnnotationTag.id != tag_id,
            AnnotationTag.team_organization_id == team_id
        ).first()
        
        if existing_tag:
            flash(f'Annotation tag "{form.name.data}" already exists!', 'danger')
            return render_template('clip/annotation_tag_form.html', form=form, tag=tag, title='Edit Annotation Tag')
        
        # Check for circular parent relationship
        parent_id = form.parent_tag_id.data if form.parent_tag_id.data > 0 else None
        if parent_id:
            # Check if the new parent is actually a descendant of this tag
            potential_parent = AnnotationTag.query.filter_by(
                id=parent_id, team_organization_id=team_id).first()
            if not potential_parent:
                flash('Parent tag not found.', 'danger')
                return render_template('clip/annotation_tag_form.html', form=form, tag=tag, title='Edit Annotation Tag')
            current_check = potential_parent
            while current_check:
                if current_check.id == tag_id:
                    flash('Cannot set parent tag: This would create a circular relationship!', 'danger')
                    return render_template('clip/annotation_tag_form.html', form=form, tag=tag, title='Edit Annotation Tag')
                current_check = current_check.parent
        
        tag.name = form.name.data
        tag.category = form.category.data
        tag.parent_tag_id = parent_id
        tag.color = form.color.data
        tag.description = form.description.data
        tag.is_active = form.is_active.data
        
        db.session.commit()
        
        flash(f'Annotation tag "{tag.name}" has been updated!', 'success')
        return redirect(url_for('clip.annotation_tags'))
    
    return render_template('clip/annotation_tag_form.html', form=form, tag=tag, title='Edit Annotation Tag')


@bp.route('/annotation-tags/delete/<int:tag_id>', methods=['POST'])
@login_required
@admin_required
def delete_annotation_tag(tag_id):
    """Delete an annotation tag"""
    team_id = get_current_team_id()
    tag = AnnotationTag.query.filter_by(id=tag_id, team_organization_id=team_id).first_or_404()
    
    name = tag.name
    
    # Clear relationships with annotations
    for annotation in tag.annotations:
        annotation.tags.remove(tag)
    
    # Update child tags to have no parent
    for child in tag.children:
        child.parent_tag_id = None
    
    db.session.delete(tag)
    db.session.commit()
    
    flash(f'Annotation tag "{name}" has been deleted!', 'success')
    return redirect(url_for('clip.annotation_tags'))
