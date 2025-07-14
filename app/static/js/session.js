window.sessionManager = {
    // CSRF token handling
    getCSRFToken: function() {
        return document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    },

    // Session deletion
    deleteSession: function(sessionId) {
        console.log('Delete session called for ID:', sessionId);
        
        if (confirm('Are you sure you want to delete this session? This cannot be undone.')) {
            const csrfToken = this.getCSRFToken();
            console.log('CSRF Token:', csrfToken);
            
            fetch(`/sessions/delete/${sessionId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                credentials: 'same-origin'
            })
            .then(response => {
                console.log('Response status:', response.status);
                return response.json();
            })
            .then(data => {
                console.log('Response data:', data);
                if (data.success) {
                    window.location.reload();
                } else {
                    this.showAlert('Error: ' + (data.message || 'Failed to delete session'), 'danger');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                this.showAlert('Failed to delete session. Please try again.', 'danger');
            });
        }
    },

    // File handling
    handleFileUpload: function(fileInput, previewElement, options = {}) {
        const file = fileInput.files[0];
        if (file) {
            if (this.validateFile(file)) {
                // Create preview
                this.previewFile(file, previewElement);
                
                // If auto-upload is enabled, perform upload
                if (options.autoUpload) {
                    return this.uploadFileToS3(file, options.uploadUrl, options.onSuccess, options.onError);
                }
                return true;
            }
        }
        return false;
    },

    validateFile: function(file) {
        const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'application/pdf'];
        const maxSize = 10 * 1024 * 1024; // 10MB

        if (!validTypes.includes(file.type)) {
            this.showAlert('Please upload a valid file type (JPG, PNG, GIF, or PDF).', 'danger');
            return false;
        }

        if (file.size > maxSize) {
            this.showAlert('File size must be less than 10MB.', 'danger');
            return false;
        }

        return true;
    },

    previewFile: function(file, previewElement) {
        if (!previewElement) return;

        if (file.type.startsWith('image/')) {
            const reader = new FileReader();
            reader.onload = function(e) {
                if (previewElement.tagName === 'IMG') {
                    previewElement.src = e.target.result;
                } else {
                    previewElement.style.backgroundImage = `url(${e.target.result})`;
                }
                previewElement.style.display = 'block';
            };
            reader.readAsDataURL(file);
        } else {
            // For non-image files, show an icon or filename
            previewElement.innerHTML = `
                <div class="file-preview">
                    <i class="fas fa-file"></i>
                    <span>${file.name}</span>
                </div>
            `;
            previewElement.style.display = 'block';
        }
    },

    uploadFileToS3: function(file, uploadUrl, onSuccess, onError) {
        const formData = new FormData();
        formData.append('file', file);

        fetch(uploadUrl, {
            method: 'POST',
            headers: {
                'X-CSRFToken': this.getCSRFToken()
            },
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                if (onSuccess) onSuccess(data);
                this.showAlert('File uploaded successfully', 'success');
            } else {
                throw new Error(data.message || 'Upload failed');
            }
        })
        .catch(error => {
            console.error('Upload error:', error);
            if (onError) onError(error);
            this.showAlert('Failed to upload file: ' + error.message, 'danger');
        });
    },

    // S3 URL handling
    handleS3Url: function(url, element) {
        if (!url) return;

        if (element.tagName === 'IMG') {
            element.src = url;
        } else if (element.tagName === 'A') {
            element.href = url;
        } else {
            element.style.backgroundImage = `url(${url})`;
        }
    },

    // Utility functions
    showAlert: function(message, type = 'info') {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
        alertDiv.style.top = '20px';
        alertDiv.style.right = '20px';
        alertDiv.style.zIndex = '9999';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;

        document.body.appendChild(alertDiv);

        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    },

    // Form handling
    handleFormSubmit: function(form, options = {}) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            const formData = new FormData(form);
            const fileInputs = form.querySelectorAll('input[type="file"]');

            // Handle file uploads first if needed
            for (const fileInput of fileInputs) {
                if (fileInput.files.length > 0) {
                    const file = fileInput.files[0];
                    if (this.validateFile(file)) {
                        formData.append(fileInput.name, file);
                    } else {
                        return; // Stop if file validation fails
                    }
                }
            }

            try {
                const response = await fetch(form.action, {
                    method: form.method,
                    headers: {
                        'X-CSRFToken': this.getCSRFToken()
                    },
                    body: formData
                });

                const data = await response.json();

                if (data.success) {
                    this.showAlert(data.message || 'Success!', 'success');
                    if (options.onSuccess) options.onSuccess(data);
                } else {
                    throw new Error(data.message || 'Submission failed');
                }
            } catch (error) {
                console.error('Form submission error:', error);
                this.showAlert(error.message, 'danger');
                if (options.onError) options.onError(error);
            }
        });
    },

    // Initialize
    init: function() {
        // Initialize file upload handlers
        document.querySelectorAll('[data-upload-preview]').forEach(input => {
            const previewEl = document.getElementById(input.dataset.uploadPreview);
            if (previewEl) {
                input.addEventListener('change', () => {
                    this.handleFileUpload(input, previewEl, {
                        autoUpload: input.dataset.autoUpload === 'true',
                        uploadUrl: input.dataset.uploadUrl,
                        onSuccess: (data) => {
                            if (input.dataset.updateField) {
                                document.getElementById(input.dataset.updateField).value = data.url;
                            }
                        }
                    });
                });
            }
        });

        // Initialize forms with file uploads
        document.querySelectorAll('form[data-handle-upload]').forEach(form => {
            this.handleFormSubmit(form, {
                onSuccess: (data) => {
                    if (form.dataset.redirectUrl) {
                        window.location.href = form.dataset.redirectUrl;
                    }
                }
            });
        });

        console.log('Session manager initialized');
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    sessionManager.init();
});

// Export for use in other scripts
window.sessionManager = sessionManager;
