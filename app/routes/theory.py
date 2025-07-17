# app/routes/theory.py
from flask import current_app, Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models.theory import TheorySection, TheoryTopic, TheoryVideo, TheoryTag
from app.forms.theory import TheorySectionForm, TheoryTopicForm, TheoryVideoForm
from app.utils.utils import save_uploaded_file
import os
from werkzeug.utils import secure_filename
from datetime import datetime
from app.utils.utils import admin_required

bp = Blueprint('theory', __name__, url_prefix='/theory')

# Main Routes
@bp.route('/')
@login_required
def index():
    sections = TheorySection.query.order_by(TheorySection.order).all()
    return render_template('theory/index.html', sections=sections)

@bp.route('/section/<string:slug>')
@login_required
def section(slug):
    section = TheorySection.query.filter_by(slug=slug).first_or_404()
    topics = section.topics.order_by(TheoryTopic.order).all()
    return render_template('theory/section.html', section=section, topics=topics)

@bp.route('/topic/<int:topic_id>')
@login_required
def topic(topic_id):
    try:
        topic = TheoryTopic.query.get_or_404(topic_id)
        return render_template('theory/topic.html', 
                             topic=topic,
                             title=topic.name)
    except Exception as e:
        current_app.logger.error(f"Error viewing topic {topic_id}: {str(e)}")
        flash('Error loading topic content.', 'danger')
        return redirect(url_for('theory.index'))

# Section Management
@bp.route('/add_section', methods=['GET', 'POST'])
@login_required
@admin_required
def add_section():
    form = TheorySectionForm()
    if form.validate_on_submit():
        section = TheorySection(
            name=form.name.data,
            description=form.description.data,
            order=form.order.data
        )
        db.session.add(section)
        try:
            db.session.commit()
            flash(f'Section "{section.name}" has been created!', 'success')
            return redirect(url_for('theory.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating section: {str(e)}', 'danger')
    
    return render_template('theory/section_form.html', form=form, title='Add Section')

@bp.route('/edit_section/<int:section_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_section(section_id):
    section = TheorySection.query.get_or_404(section_id)
    form = TheorySectionForm(obj=section)
    
    if form.validate_on_submit():
        section.name = form.name.data
        section.description = form.description.data
        section.order = form.order.data
        
        try:
            db.session.commit()
            flash(f'Section "{section.name}" has been updated!', 'success')
            return redirect(url_for('theory.section', slug=section.slug))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating section: {str(e)}', 'danger')
    
    return render_template('theory/section_form.html', form=form, section=section, title='Edit Section')

@bp.route('/delete_section/<int:section_id>', methods=['POST'])
@login_required
@admin_required
def delete_section(section_id):
    section = TheorySection.query.get_or_404(section_id)
    name = section.name
    
    try:
        db.session.delete(section)
        db.session.commit()
        flash(f'Section "{name}" has been deleted!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting section: {str(e)}', 'danger')
    
    return redirect(url_for('theory.index'))

# Topic Management
@bp.route('/add_topic', methods=['GET', 'POST'])
@login_required
@admin_required
def add_topic():
    form = TheoryTopicForm()
    form.section_id.choices = [(s.id, s.name) for s in TheorySection.query.order_by(TheorySection.name).all()]
    
    if form.validate_on_submit():
        topic = TheoryTopic(
            name=form.name.data,
            content=form.content.data,
            section_id=form.section_id.data,
            order=form.order.data,
            created_by=current_user.id,
            image_url=form.image_url.data  # Use the URL directly
        )
        
        db.session.add(topic)
        try:
            db.session.commit()
            flash(f'Topic "{topic.name}" has been created!', 'success')
            return redirect(url_for('theory.topic', topic_id=topic.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating topic: {str(e)}', 'danger')
    
    return render_template('theory/topic_form.html', form=form, title='Add Topic')

@bp.route('/edit_topic/<int:topic_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_topic(topic_id):
    topic = TheoryTopic.query.get_or_404(topic_id)
    form = TheoryTopicForm(obj=topic)
    form.section_id.choices = [(s.id, s.name) for s in TheorySection.query.order_by(TheorySection.name).all()]
    
    if form.validate_on_submit():
        topic.name = form.name.data
        topic.content = form.content.data
        topic.section_id = form.section_id.data
        topic.order = form.order.data
        topic.image_url = form.image_url.data  # Update the URL directly
        
        if form.related_drills.data:
            topic.related_drills = [form.related_drills.data]
            
        try:
            db.session.commit()
            flash(f'Topic "{topic.name}" has been updated!', 'success')
            return redirect(url_for('theory.topic', topic_id=topic.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating topic: {str(e)}', 'danger')
    
    return render_template('theory/topic_form.html', form=form, topic=topic, title='Edit Topic')

@bp.route('/delete_topic/<int:topic_id>', methods=['POST'])
@login_required
@admin_required
def delete_topic(topic_id):
    topic = TheoryTopic.query.get_or_404(topic_id)
    section_slug = topic.section.slug
    name = topic.name
    
    try:
        db.session.delete(topic)
        db.session.commit()
        flash(f'Topic "{name}" has been deleted!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting topic: {str(e)}', 'danger')
    
    return redirect(url_for('theory.section', slug=section_slug))

# Video Management
@bp.route('/add_video/<int:topic_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def add_video(topic_id):
    topic = TheoryTopic.query.get_or_404(topic_id)
    form = TheoryVideoForm()
    
    if form.validate_on_submit():
        video = TheoryVideo(
            topic_id=topic_id,
            title=form.title.data,
            url=form.url.data,
            description=form.description.data,
            order=form.order.data
        )
        db.session.add(video)
        try:
            db.session.commit()
            flash(f'Video "{video.title}" has been added!', 'success')
            return redirect(url_for('theory.topic', topic_id=topic_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding video: {str(e)}', 'danger')
    
    return render_template('theory/video_form.html', form=form, topic=topic, title='Add Video')

# Error Handlers
@bp.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@bp.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500
