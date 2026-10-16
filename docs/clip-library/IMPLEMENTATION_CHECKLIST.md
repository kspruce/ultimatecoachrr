# Implementation Checklist

Use this checklist to track your implementation progress.

## Pre-Implementation
- [ ] **Backup your database** 
  ```bash
  # For SQLite
  cp instance/your_database.db instance/your_database.backup.db
  
  # For PostgreSQL
  pg_dump your_database > backup.sql
  ```
- [ ] **Backup your code**
  ```bash
  git commit -am "Pre-enhancement backup"
  git tag pre-annotation-enhancement
  ```
- [ ] **Review all provided files**
  - Read IMPLEMENTATION_GUIDE.md
  - Review DELIVERABLES_SUMMARY.md
  - Check SYSTEM_DIAGRAMS.md for architecture understanding

## Phase 1: Model Updates (30-60 minutes)

### Update Clip Model
- [ ] Replace `app/models/clip.py` with new `clip_model.py`
- [ ] Verify imports work correctly
- [ ] Check for any custom modifications you made to preserve

### Update Annotation Model
- [ ] Replace `app/models/annotation.py` with new version
- [ ] Verify ClipAnnotation class exists
- [ ] Verify AnnotationTag class exists
- [ ] Check association tables are defined

### Update Models __init__.py
- [ ] Open `app/models/__init__.py`
- [ ] Add import: `from app.models.annotation import ClipAnnotation, AnnotationTag`
- [ ] Verify no import errors:
  ```bash
  python -c "from app.models import ClipAnnotation, AnnotationTag; print('Success!')"
  ```

## Phase 2: Forms (15-30 minutes)

### Create/Update Annotation Forms
- [ ] Create `app/forms/annotation_forms.py` (or update if exists)
- [ ] Copy contents from provided `annotation_forms.py`
- [ ] Verify all imports work
- [ ] Test form import:
  ```bash
  python -c "from app.forms.annotation_forms import AnnotationForm; print('Success!')"
  ```

### Update Clip Forms (if needed)
- [ ] Check if your `app/forms/clip.py` needs updates
- [ ] Compare with ROUTE_EXAMPLES.md

## Phase 3: Database Migration (30-60 minutes)

### Prepare for Migration
- [ ] Stop your Flask application
- [ ] Ensure database connection works
- [ ] Check Flask-Migrate is installed:
  ```bash
  pip list | grep Flask-Migrate
  ```

### Run Migration

**Option A: Using Flask-Migrate (Recommended)**
- [ ] Generate migration:
  ```bash
  flask db migrate -m "Add enhanced clip and annotation features"
  ```
- [ ] Review the generated migration file in `migrations/versions/`
- [ ] Apply migration:
  ```bash
  flask db upgrade
  ```
- [ ] Verify tables exist:
  ```bash
  flask shell
  >>> from app import db
  >>> db.engine.table_names()
  ```

**Option B: Manual Migration**
- [ ] Copy `migration_script.py` to your project
- [ ] Run in Flask shell:
  ```python
  from migration_script import upgrade_database
  upgrade_database()
  ```

### Verify Migration Success
- [ ] Check new tables exist: `annotation_tag`, `annotation_tag_relation`, `annotation_player`
- [ ] Check new columns exist in `clip_annotation`: `user_id`, `title`, `is_key_moment`, `visibility`
- [ ] Check new columns exist in `clip`: `created_by_id`, `is_featured`, `view_count`
- [ ] Check updated columns in `clip_tag`: `parent_tag_id`, `color`, `description`, `is_active`

## Phase 4: Populate Tags (15 minutes)

### Add Tag Management Command
- [ ] Copy `tag_management.py` to your project (e.g., `app/utils/tag_management.py`)
- [ ] Register commands in your app initialization
- [ ] Verify command works:
  ```bash
  flask --help | grep populate-tags
  ```

### Populate Default Tags
- [ ] Run tag population:
  ```bash
  flask populate-tags
  ```
- [ ] Verify tags created:
  ```bash
  flask shell
  >>> from app.models.clip import ClipTag
  >>> from app.models.annotation import AnnotationTag
  >>> print(f"Clip tags: {ClipTag.query.count()}")
  >>> print(f"Annotation tags: {AnnotationTag.query.count()}")
  ```
- [ ] Expected: ~15-20 ClipTags, 60+ AnnotationTags

## Phase 5: Update Routes (60-90 minutes)

### Backup Current Routes
- [ ] Copy current `app/routes/clip.py` to `clip.py.backup`

### Add New Routes
Reference `ROUTE_EXAMPLES.md` for complete implementation.

- [ ] Add annotation routes:
  - [ ] `GET/POST /clip/<id>/annotation/add` - Create annotation
  - [ ] `GET/POST /annotation/<id>/edit` - Update annotation  
  - [ ] `POST /annotation/<id>/delete` - Delete annotation

- [ ] Add annotation tag routes (if needed):
  - [ ] `GET /annotation-tags` - List annotation tags
  - [ ] `GET/POST /annotation-tags/add` - Create annotation tag

- [ ] Update existing routes:
  - [ ] Update `view_clip` to handle annotation filtering
  - [ ] Update `add_clip` to track `created_by_id`

- [ ] Add AJAX endpoints:
  - [ ] `GET /get_points/<game_id>` - Get points for game
  - [ ] `GET /get_game_link/<game_id>` - Get game's YouTube link

### Test Routes
- [ ] Start Flask app: `flask run`
- [ ] Test each route manually:
  - [ ] Can view clips
  - [ ] Can add clip
  - [ ] Can add annotation
  - [ ] Can edit annotation
  - [ ] Can delete annotation
  - [ ] Filters work

## Phase 6: Update Templates (30-45 minutes)

### Update View Clip Template
- [ ] Backup current: `cp app/templates/clip/view_clip.html app/templates/clip/view_clip.html.backup`
- [ ] Replace with new `view_clip.html`
- [ ] Test video player loads
- [ ] Test annotations display
- [ ] Test timestamp clicking

### Create Annotation Templates (if needed)
- [ ] Create `app/templates/clip/add_annotation.html`
- [ ] Create `app/templates/clip/edit_annotation.html`
- [ ] Verify forms render correctly

### Update Other Templates
- [ ] Check `index.html` shows new features
- [ ] Check `game_clips.html` if used
- [ ] Check `point_clips.html` if used

## Phase 7: Testing (60 minutes)

### Basic Functionality
- [ ] Create a test clip
- [ ] Add video tags to clip
- [ ] Add annotation to clip
- [ ] Add multiple annotation tags
- [ ] Tag players in annotation
- [ ] Mark annotation as key moment
- [ ] Test visibility controls

### Permission Testing
- [ ] Test as admin: can edit any annotation
- [ ] Test as coach: can edit own annotations
- [ ] Test as player: can only edit own annotations
- [ ] Test annotation visibility (team/coaches/private)

### Filter Testing
- [ ] Filter by event type
- [ ] Filter by creator
- [ ] Filter by key moments only
- [ ] Filter clips by tags
- [ ] Filter clips by players

### Edge Cases
- [ ] Create annotation at timestamp 0
- [ ] Create annotation with no tags
- [ ] Create annotation with no players
- [ ] Delete clip with annotations (should cascade)
- [ ] Edit someone else's annotation (should deny)

## Phase 8: Documentation & Training (30 minutes)

### Create User Documentation
- [ ] Share USER_QUICK_REFERENCE.md with team
- [ ] Create quick video tutorial (5-10 minutes)
- [ ] Schedule training session

### Update Internal Docs
- [ ] Document new features in your wiki/docs
- [ ] Update API documentation if you have one
- [ ] Add tag reference guide

## Phase 9: Deployment (30 minutes)

### Pre-Deployment
- [ ] Run all tests in production-like environment
- [ ] Check database migration on staging
- [ ] Review logs for errors

### Deploy to Production
- [ ] Deploy code changes
- [ ] Run database migration
- [ ] Populate tags
- [ ] Monitor for errors

### Post-Deployment
- [ ] Verify application loads
- [ ] Test critical paths
- [ ] Monitor error logs
- [ ] Check database performance

## Phase 10: Monitoring & Optimization (Ongoing)

### Week 1
- [ ] Monitor usage patterns
- [ ] Collect user feedback
- [ ] Fix any bugs found
- [ ] Optimize slow queries if any

### Week 2-4
- [ ] Review tag usage (which tags are used most?)
- [ ] Add any missing tags requested by users
- [ ] Consider adding custom tags feature
- [ ] Plan next enhancements

## Rollback Plan (If Needed)

If something goes wrong:

1. **Rollback Code**
   ```bash
   git checkout pre-annotation-enhancement
   ```

2. **Rollback Database**
   ```bash
   flask db downgrade
   # Or restore from backup
   ```

3. **Restore from Backup**
   ```bash
   # For SQLite
   cp instance/your_database.backup.db instance/your_database.db
   
   # For PostgreSQL
   psql your_database < backup.sql
   ```

## Common Issues & Solutions

### Issue: Migration fails with "table already exists"
**Solution:** Drop the problematic table and re-run migration, or use `extend_existing=True` in model

### Issue: Forms don't show tags
**Solution:** Verify tags were populated with `flask populate-tags`

### Issue: Annotations don't show up
**Solution:** Check visibility settings and user permissions

### Issue: Video doesn't play
**Solution:** Verify YouTube link format and embed URL generation

### Issue: Timestamps don't work
**Solution:** Check JavaScript in template, verify YouTube API access

## Success Criteria

You've successfully implemented when:
- [ ] ✅ All clips display with tags
- [ ] ✅ Users can add annotations with tags
- [ ] ✅ Annotations show creator names
- [ ] ✅ Filtering works correctly
- [ ] ✅ Permissions are enforced
- [ ] ✅ Key moments are highlighted
- [ ] ✅ Timestamp clicking jumps video
- [ ] ✅ No errors in logs
- [ ] ✅ Users are trained and happy!

## Post-Implementation

### Celebrate! 🎉
You've successfully enhanced your clip library with:
- 100+ tactical tags
- Multi-user annotations
- Hierarchical organization
- Enhanced coaching tools

### Next Steps
- Gather user feedback
- Plan additional features (see IMPLEMENTATION_GUIDE.md)
- Share with other Ultimate teams?
- Consider open-sourcing your improvements!

---

## Need Help?

1. Check IMPLEMENTATION_GUIDE.md for detailed instructions
2. Review ROUTE_EXAMPLES.md for code samples
3. Look at SYSTEM_DIAGRAMS.md for architecture
4. Check Flask/SQLAlchemy logs for errors
5. Test in Flask shell for debugging

## Time Estimate

Total implementation time: **4-6 hours** (depending on experience level)
- Models: 30-60 min
- Forms: 15-30 min
- Migration: 30-60 min
- Tags: 15 min
- Routes: 60-90 min
- Templates: 30-45 min
- Testing: 60 min
- Deployment: 30 min
- Documentation: 30 min

Good luck! 🥏
