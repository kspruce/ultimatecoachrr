const playbookManager = {
    // CSRF token handling
    getCSRFToken: function() {
        return document.querySelector('meta[name="csrf-token"]').content;
    },

    // Delete handlers
    deletePlay: function(playId) {
        if (!confirm('Are you sure you want to delete this play?')) {
            return;
        }

        fetch(`/playbook/plays/${playId}/delete`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Dispatch custom event for successful deletion
                window.dispatchEvent(new CustomEvent('playDeleted', {
                    detail: { playId: playId }
                }));
                
                // Show success message
                this.showAlert(data.message, 'success');
                
                // Redirect to index if we're on the detail page
                if (window.location.pathname.includes('/plays/')) {
                    window.location.href = '/playbook';
                } else {
                    // Remove the play element from the list
                    document.querySelector(`[data-play-id="${playId}"]`)?.remove();
                }
            } else {
                this.showAlert(data.message, 'danger');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            this.showAlert('An error occurred while deleting the play.', 'danger');
        });
    },

    deleteFormation: function(formationId) {
        if (!confirm('Are you sure you want to delete this formation? All plays using this formation will need to be updated.')) {
            return;
        }

        fetch(`/playbook/formations/${formationId}/delete`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                this.showAlert(data.message, 'success');
                document.querySelector(`[data-formation-id="${formationId}"]`)?.remove();
            } else {
                this.showAlert(data.message, 'danger');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            this.showAlert('An error occurred while deleting the formation.', 'danger');
        });
    },

    // Image handling
    initImagePreviews: function() {
        document.querySelectorAll('.diagram-upload').forEach(input => {
            input.addEventListener('change', function(e) {
                const file = this.files[0];
                if (file) {
                    if (this.validateImage(file)) {
                        this.previewImage(file, this.nextElementSibling);
                    }
                }
            }.bind(this));
        });
    },

    validateImage: function(file) {
        const validTypes = ['image/jpeg', 'image/png', 'image/gif'];
        const maxSize = 5 * 1024 * 1024; // 5MB

        if (!validTypes.includes(file.type)) {
            this.showAlert('Please upload a valid image file (JPG, PNG, or GIF).', 'danger');
            return false;
        }

        if (file.size > maxSize) {
            this.showAlert('Image file size must be less than 5MB.', 'danger');
            return false;
        }

        return true;
    },

    previewImage: function(file, previewElement) {
        const reader = new FileReader();
        reader.onload = function(e) {
            previewElement.src = e.target.result;
            previewElement.style.display = 'block';
            
            // Store original file for form submission
            previewElement.dataset.originalFile = file;
        };
        reader.readAsDataURL(file);
    },

    // Add method to handle S3 URLs
    handleS3Image: function(s3Url, previewElement) {
        if (s3Url) {
            previewElement.src = s3Url;
            previewElement.style.display = 'block';
        } else {
            previewElement.style.display = 'none';
        }
    },

    // Form handling
    initFormValidation: function() {
        document.querySelectorAll('form').forEach(form => {
            form.addEventListener('submit', function(e) {
                if (!form.checkValidity()) {
                    e.preventDefault();
                    e.stopPropagation();
                }
                form.classList.add('was-validated');
            });
        });
    },

    // Tag handling
    initTagManagement: function() {
        const tagSelect = document.getElementById('tags');
        if (tagSelect) {
            // Initialize tag selection (you could use Select2 or similar)
            $(tagSelect).select2({
                placeholder: 'Select or create tags...',
                tags: true,
                tokenSeparators: [',', ' '],
                maximumSelectionLength: 5
            });
        }
    },

    // Formation selection handling
    initFormationSelection: function() {
        const formationSelect = document.getElementById('formation_id');
        if (formationSelect) {
            formationSelect.addEventListener('change', function(e) {
                const formationId = this.value;
                if (formationId > 0) {
                    playbookManager.loadFormationDetails(formationId);
                }
            });
        }
    },

    loadFormationDetails: function(formationId) {
        fetch(`/playbook/formations/${formationId}`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Update formation preview if it exists
                    const preview = document.getElementById('formation-preview');
                    if (preview && data.formation.diagram_url) {
                        this.handleS3Image(data.formation.diagram_url, preview);
                    }
                }
            })
            .catch(error => console.error('Error:', error));
    },

    // Utility functions
    showAlert: function(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.role = 'alert';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;

        // Find or create alerts container
        let alertsContainer = document.getElementById('alerts-container');
        if (!alertsContainer) {
            alertsContainer = document.createElement('div');
            alertsContainer.id = 'alerts-container';
            alertsContainer.className = 'position-fixed top-0 end-0 p-3';
            document.body.appendChild(alertsContainer);
        }

        alertsContainer.appendChild(alertDiv);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    },

    // Search and filter functionality
    initSearch: function() {
        const searchInput = document.getElementById('playbook-search');
        if (searchInput) {
            searchInput.addEventListener('input', this.debounce(function(e) {
                playbookManager.filterPlays(e.target.value);
            }, 300));
        }
    },

    filterPlays: function(query) {
        const plays = document.querySelectorAll('.play-item');
        plays.forEach(play => {
            const text = play.textContent.toLowerCase();
            const matches = text.includes(query.toLowerCase());
            play.style.display = matches ? '' : 'none';
        });
    },

    debounce: function(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    // File upload handling for S3
    handleFileUpload: function(fileInput, formData) {
        const file = fileInput.files[0];
        if (file) {
            formData.append('file', file);
            return true;
        }
        return false;
    },

    // Initialization
    init: function() {
        // Initialize all components
        this.initImagePreviews();
        this.initFormValidation();
        this.initTagManagement();
        this.initFormationSelection();
        this.initSearch();

        // Initialize tooltips
        var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });

        console.log('Playbook Manager initialized');
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    playbookManager.init();
});

// Export for use in other scripts
window.playbookManager = playbookManager;
