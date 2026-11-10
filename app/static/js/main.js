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

// Signing out forgets the scouting game cards saved on this device for offline use
document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!(form.matches && form.matches('form[action$="/logout"]')) || !('caches' in window)) return;
    e.preventDefault();
    caches.keys().then(function (keys) {
        return Promise.all(keys.filter(function (k) { return k.indexOf('scouting-cards-') === 0; })
                               .map(function (k) { return caches.delete(k); }));
    }).catch(function () {}).then(function () { form.submit(); });
});

// "On this page" strip for long pages: put <nav class="uc-section-nav"
// data-section-nav></nav> where it should sit and it lists every card
// heading below it, sticks under the navbar and marks the one in view.
document.addEventListener('DOMContentLoaded', function () {
  var nav = document.querySelector('[data-section-nav]');
  if (!nav) return;
  var skip = (nav.dataset.skip || '').split('|').filter(Boolean);
  var sections = [];
  document.querySelectorAll('.card > .card-header h5').forEach(function (heading) {
    if (!(nav.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING)) return;
    if (heading.closest('.modal, .tab-pane:not(.active)')) return;
    // The heading's own words, without tooltips' icons or small print
    var label = '';
    heading.childNodes.forEach(function (node) {
      if (node.nodeType === Node.TEXT_NODE) label += node.textContent;
    });
    label = label.replace(/\s+/g, ' ').trim();
    if (!label || skip.indexOf(label) !== -1) return;
    var card = heading.closest('.card');
    if (!card.id) card.id = 'section-' + label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    sections.push({card: card, label: label});
  });
  if (sections.length < 3) { nav.hidden = true; return; }

  var links = sections.map(function (section) {
    var a = document.createElement('a');
    a.href = '#' + section.card.id;
    a.textContent = section.label;
    nav.appendChild(a);
    return a;
  });
  if (!('IntersectionObserver' in window)) return;
  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      links.forEach(function (a, i) {
        var on = sections[i].card === entry.target;
        a.classList.toggle('on', on);
        if (on && nav.scrollWidth > nav.clientWidth) {
          nav.scrollTo({left: a.offsetLeft - nav.clientWidth / 2 + a.offsetWidth / 2, behavior: 'smooth'});
        }
      });
    });
  }, {rootMargin: '-25% 0px -65% 0px'});
  sections.forEach(function (section) { observer.observe(section.card); });
});

// The phone tab bar's "More" opens the full menu (the navbar is sticky, so it's on screen)
document.addEventListener('DOMContentLoaded', function () {
  var more = document.getElementById('ucTabbarMore');
  var menu = document.getElementById('navbarNav');
  if (!more || !menu || !window.bootstrap) return;
  more.addEventListener('click', function () {
    var collapse = bootstrap.Collapse.getOrCreateInstance(menu, {toggle: false});
    collapse.toggle();
  });
  menu.addEventListener('shown.bs.collapse', function () { more.setAttribute('aria-expanded', 'true'); });
  menu.addEventListener('hidden.bs.collapse', function () { more.setAttribute('aria-expanded', 'false'); });
});

// "/" opens Search, unless you're typing somewhere
document.addEventListener('keydown', function (event) {
  if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey) return;
  var el = event.target;
  if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
  var link = document.getElementById('ucSearchLink');
  if (!link) return;
  event.preventDefault();
  window.location.href = link.href;
});
