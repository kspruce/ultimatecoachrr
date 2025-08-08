/**
 * Session Module Scripts
 * Enhances the user experience for session management
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    });
    
    // Initialize popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'))
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl)
    });
    
    // Handle session type filter changes
    const sessionTypeFilter = document.getElementById('session_type');
    if (sessionTypeFilter) {
        sessionTypeFilter.addEventListener('change', function() {
            // Add visual indicator of active filter
            if (this.value) {
                this.classList.add('border-primary');
            } else {
                this.classList.remove('border-primary');
            }
        });
        
        // Initialize on page load
        if (sessionTypeFilter.value) {
            sessionTypeFilter.classList.add('border-primary');
        }
    }
    
    // Handle recurring session checkbox
    const isRecurringCheckbox = document.getElementById('is_recurring');
    const recurrencePatternDiv = document.getElementById('recurrence-pattern-div');
    
    if (isRecurringCheckbox && recurrencePatternDiv) {
        // Show/hide recurrence pattern based on checkbox
        function updateRecurrencePattern() {
            if (isRecurringCheckbox.checked) {
                recurrencePatternDiv.style.display = 'block';
                // Use animation for smoother transition
                recurrencePatternDiv.classList.add('fade-in');
            } else {
                recurrencePatternDiv.style.display = 'none';
                recurrencePatternDiv.classList.remove('fade-in');
            }
        }
        
        // Initial update
        updateRecurrencePattern();
        
        // Add event listener
        isRecurringCheckbox.addEventListener('change', updateRecurrencePattern);
    }
    
    // Add animation to session cards
    const sessionCards = document.querySelectorAll('.session-card');
    if (sessionCards.length > 0) {
        sessionCards.forEach((card, index) => {
            // Stagger the animation for a nice effect
            setTimeout(() => {
                card.classList.add('fade-in');
            }, index * 100);
        });
    }
    
    // Enhance mobile experience for tables
    const tables = document.querySelectorAll('.table-responsive');
    if (tables.length > 0 && window.innerWidth < 768) {
        tables.forEach(table => {
            // Add horizontal scroll indicator
            const scrollIndicator = document.createElement('div');
            scrollIndicator.className = 'text-muted text-center mt-2';
            scrollIndicator.innerHTML = '<small><i class="bi bi-arrow-left-right"></i> Scroll horizontally to see more</small>';
            table.after(scrollIndicator);
        });
    }
    
    // Add confirmation for delete actions
    const deleteButtons = document.querySelectorAll('[data-confirm]');
    if (deleteButtons.length > 0) {
        deleteButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                if (!confirm(this.dataset.confirm)) {
                    e.preventDefault();
                }
            });
        });
    }
});

/**
 * Filter sessions by type dynamically without page reload
 * This is an enhancement that could be implemented if using AJAX
 */
function filterSessionsByType(type) {
    const sessionRows = document.querySelectorAll('.session-row');
    
    if (sessionRows.length > 0) {
        sessionRows.forEach(row => {
            const sessionType = row.dataset.sessionType;
            
            if (!type || sessionType === type) {
                row.style.display = '';
            } else {
                row.style.display = 'none';
            }
        });
    }
}

/**
 * Preview session components when hovering over them in the list
 */
function initComponentPreview() {
    const componentLinks = document.querySelectorAll('.component-preview-link');
    const previewContainer = document.getElementById('component-preview');
    
    if (componentLinks.length > 0 && previewContainer) {
        componentLinks.forEach(link => {
            link.addEventListener('mouseenter', function() {
                const componentId = this.dataset.componentId;
                const componentTitle = this.dataset.componentTitle;
                const componentDescription = this.dataset.componentDescription;
                
                previewContainer.innerHTML = `
                    <div class="card">
                        <div class="card-header">${componentTitle}</div>
                        <div class="card-body">
                            <p>${componentDescription || 'No description available'}</p>
                        </div>
                    </div>
                `;
                
                previewContainer.style.display = 'block';
            });
            
            link.addEventListener('mouseleave', function() {
                previewContainer.style.display = 'none';
            });
        });
    }
}