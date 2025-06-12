// Main JavaScript for Ultimate Coach app

// Global configuration
const UltimateCoach = {
    config: {
        maxFileSize: 10 * 1024 * 1024, // 10MB
        allowedFileTypes: {
            images: ['image/jpeg', 'image/png', 'image/gif'],
            documents: ['application/pdf'],
            all: ['image/jpeg', 'image/png', 'image/gif', 'application/pdf']
        },
        s3: {
            baseUrl: '' // Will be set from meta tag
        }
    },

    // File handling utilities
    fileUtils: {
        validateFile: function(file, allowedTypes = UltimateCoach.config.allowedFileTypes.all) {
            if (!file) return false;

            // Check file type
            if (!allowedTypes.includes(file.type)) {
                UltimateCoach.ui.showAlert(
                    'Invalid file type. Allowed types: ' + allowedTypes.join(', '),
                    'danger'
                );
                return false;
            }

            // Check file size
            if (file.size > UltimateCoach.config.maxFileSize) {
                UltimateCoach.ui.showAlert(
                    `File size must be less than ${UltimateCoach.config.maxFileSize / (1024 * 1024)}MB`,
                    'danger'
                );
                return false;
            }

            return true;
        },

        createPreview: function(file, previewElement) {
            if (!file || !previewElement) return;

            const reader = new FileReader();

            reader.onload = function(e) {
                if (file.type.startsWith('image/')) {
                    if (previewElement.tagName === 'IMG') {
                        previewElement.src = e.target.result;
                    } else {
                        previewElement.style.backgroundImage = `url(${e.target.result})`;
                    }
                } else {
                    // For non-image files
                    previewElement.innerHTML = `
                        <div class="file-preview">
                            <i class="fas fa-file"></i>
                            <span>${file.name}</span>
                        </div>
                    `;
                }
                previewElement.style.display = 'block';
            };

            reader.onerror = function() {
                UltimateCoach.ui.showAlert('Error creating file preview', 'danger');
            };

            reader.readAsDataURL(file);
        }
    },

    // UI utilities
    ui: {
        showAlert: function(message, type = 'info', duration = 5000) {
            const alertDiv = document.createElement('div');
            alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
            alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999; max-width: 90%;';
            alertDiv.innerHTML = `
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            `;

            document.body.appendChild(alertDiv);

            // Remove alert after duration
            setTimeout(() => {
                alertDiv.remove();
            }, duration);
        },

        showLoading: function(element, message = 'Loading...') {
            element.classList.add('position-relative');
            const spinner = document.createElement('div');
            spinner.className = 'loading-spinner';
            spinner.innerHTML = `
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">${message}</span>
                </div>
                <div class="loading-message">${message}</div>
            `;
            element.appendChild(spinner);
        },

        hideLoading: function(element) {
            const spinner = element.querySelector('.loading-spinner');
            if (spinner) {
                spinner.remove();
            }
            element.classList.remove('position-relative');
        }
    },

    // Form handling
    forms: {
        init: function() {
            // Initialize all forms with file uploads
            document.querySelectorAll('form[data-handles-files="true"]').forEach(form => {
                this.initializeFileUploadForm(form);
            });

            // Initialize all file input fields
            document.querySelectorAll('input[type="file"][data-preview]').forEach(input => {
                this.initializeFileInput(input);
            });
        },

        initializeFileUploadForm: function(form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();

                const submitButton = form.querySelector('[type="submit"]');
                if (submitButton) {
                    submitButton.disabled = true;
                    UltimateCoach.ui.showLoading(submitButton, 'Uploading...');
                }

                try {
                    const formData = new FormData(form);
                    const response = await fetch(form.action, {
                        method: form.method,
                        headers: {
                            'X-CSRFToken': document.querySelector('[name="csrf-token"]').content
                        },
                        body: formData
                    });

                    const data = await response.json();

                    if (data.success) {
                        UltimateCoach.ui.showAlert(data.message || 'Success!', 'success');
                        if (form.dataset.redirectUrl) {
                            window.location.href = form.dataset.redirectUrl;
                        }
                    } else {
                        throw new Error(data.message || 'Submission failed');
                    }
                } catch (error) {
                    UltimateCoach.ui.showAlert(error.message, 'danger');
                } finally {
                    if (submitButton) {
                        submitButton.disabled = false;
                        UltimateCoach.ui.hideLoading(submitButton);
                    }
                }
            });
        },

        initializeFileInput: function(input) {
            const previewElement = document.getElementById(input.dataset.preview);
            if (!previewElement) return;

            input.addEventListener('change', () => {
                const file = input.files[0];
                if (file && UltimateCoach.fileUtils.validateFile(file)) {
                    UltimateCoach.fileUtils.createPreview(file, previewElement);
                }
            });
        }
    },

    // S3 handling
    s3: {
        getSignedUrl: async function(fileName, fileType) {
            try {
                const response = await fetch('/get-signed-url', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('[name="csrf-token"]').content
                    },
                    body: JSON.stringify({ fileName, fileType })
                });
                return await response.json();
            } catch (error) {
                console.error('Error getting signed URL:', error);
                throw error;
            }
        }
    },

    // Initialize the application
    init: function() {
        console.log('Ultimate Coach app initializing...');

        // Set S3 base URL from meta tag
        const s3BaseUrl = document.querySelector('meta[name="s3-base-url"]')?.content;
        if (s3BaseUrl) {
            this.config.s3.baseUrl = s3BaseUrl;
        }

        // Initialize forms
        this.forms.init();

        // Initialize tooltips
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });

        // Initialize popovers
        const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
        popoverTriggerList.map(function (popoverTriggerEl) {
            return new bootstrap.Popover(popoverTriggerEl);
        });

        console.log('Ultimate Coach app initialized');
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    UltimateCoach.init();
});

// Export for use in other scripts
window.UltimateCoach = UltimateCoach;
