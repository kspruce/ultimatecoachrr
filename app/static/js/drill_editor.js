document.addEventListener('DOMContentLoaded', function() {
    // Initialize variables
    let canvas;
    let currentTool = 'select';
    let drillId = null;

    // Get drill ID if editing an existing drill
    const drillDataEl = document.getElementById('drill-data');
    if (drillDataEl) {
        drillId = drillDataEl.dataset.drillId;
    }

    // Initialize the canvas with Fabric.js
    initCanvas();

    // Load drill data if editing an existing drill
    if (drillId) {
        loadDrillData(drillId);
    }

    // Set up event listeners
    setupEventListeners();

    function initCanvas() {
        // Create a Fabric.js canvas
        canvas = new fabric.Canvas('drill-canvas', {
            width: document.querySelector('.canvas-container').offsetWidth,
            height: document.querySelector('.canvas-container').offsetHeight,
            backgroundColor: '#ffffff',
            selection: true
        });

        // Add ultimate field background
        addFieldBackground();

        // Make canvas responsive
        window.addEventListener('resize', function() {
            resizeCanvas();
        });
    }

    function resizeCanvas() {
        const container = document.querySelector('.canvas-container');
        canvas.setDimensions({
            width: container.offsetWidth,
            height: container.offsetHeight
        });
        canvas.renderAll();
    }

    function addFieldBackground() {
        // Field background code remains the same
        // ... (keep existing field background code)
    }

    function setupEventListeners() {
        // Keep existing event listener setup
        // ... (keep existing event listener code)
    }

    // Modified save function to handle S3 upload
    function saveDrill() {
        // Create FormData object for multipart form data
        const formData = new FormData();

        // Get drill properties
        const drillData = {
            title: document.getElementById('drill-title').value || 'Untitled Drill',
            description: document.getElementById('drill-description').value || '',
            setup_instructions: document.getElementById('setup-instructions').value || '',
            skill_level: document.getElementById('skill-level').value,
            focus_area: document.getElementById('focus-area').value,
            recommended_duration: document.getElementById('recommended-duration').value,
            equipment_needed: document.getElementById('equipment-needed').value,
            min_players: document.getElementById('min-players').value || null,
            max_players: document.getElementById('max-players').value || null,
            is_public: document.getElementById('is-public').checked,
            elements: getCurrentCanvasState()
        };

        // Convert canvas to blob
        canvas.toBlob(function(blob) {
            formData.append('diagram', blob, 'diagram.png');
            formData.append('data', JSON.stringify(drillData));

            const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
            if (!csrfToken) {
                showNotification('Security token not found. Please refresh the page.', 'error');
                return;
            }

            const url = drillId ? 
                `/drills/api/drills/${drillId}` : 
                '/drills/api/drills';

            fetch(url, {
                method: drillId ? 'PUT' : 'POST',
                headers: {
                    'X-CSRFToken': csrfToken
                },
                body: formData
            })
            .then(response => {
                if (!response.ok) throw new Error('Failed to save drill');
                return response.json();
            })
            .then(data => {
                if (!drillId) {
                    drillId = data.drill_id;
                    window.history.replaceState({}, '', `/drills/editor/${drillId}`);
                }
                showNotification('Drill saved successfully!');
            })
            .catch(error => {
                console.error('Error saving drill:', error);
                showNotification('Failed to save drill: ' + error.message, 'error');
            });
        }, 'image/png');
    }

    function loadDrillData(drillId) {
        fetch(`/drills/api/drills/${drillId}`)
            .then(response => {
                if (!response.ok) throw new Error('Failed to load drill');
                return response.json();
            })
            .then(data => {
                // Set drill details
                document.getElementById('drill-title').value = data.title;
                document.getElementById('drill-description').value = data.description;
                document.getElementById('setup-instructions').value = data.setup_instructions;
                document.getElementById('skill-level').value = data.skill_level;
                document.getElementById('focus-area').value = data.focus_area;
                document.getElementById('recommended-duration').value = data.recommended_duration;
                document.getElementById('equipment-needed').value = data.equipment_needed;
                document.getElementById('min-players').value = data.min_players;
                document.getElementById('max-players').value = data.max_players;
                document.getElementById('is-public').checked = data.is_public;

                // Load diagram from S3 if available
                if (data.diagram_url) {
                    loadDiagramFromS3(data.diagram_url);
                }

                // Load elements
                if (data.elements && data.elements.length > 0) {
                    clearCanvas();
                    loadElements(data.elements);
                }
            })
            .catch(error => {
                console.error('Error loading drill:', error);
                showNotification('Failed to load drill', 'error');
            });
    }

    function loadDiagramFromS3(url) {
        fabric.Image.fromURL(url, function(img) {
            // Scale image to fit canvas while maintaining aspect ratio
            const scale = Math.min(
                canvas.width / img.width,
                canvas.height / img.height
            );

            img.set({
                scaleX: scale,
                scaleY: scale,
                left: (canvas.width - img.width * scale) / 2,
                top: (canvas.height - img.height * scale) / 2,
                selectable: false,
                evented: false
            });

            canvas.add(img);
            img.sendToBack();
            canvas.renderAll();
        }, {
            crossOrigin: 'anonymous'
        });
    }

    // Keep existing helper functions
    function getCurrentCanvasState() {
        return canvas.getObjects()
            .filter(obj => obj.type !== 'rect')
            .map(obj => ({
                type: obj.type || 'unknown',
                left: obj.left,
                top: obj.top,
                scaleX: obj.scaleX || 1,
                scaleY: obj.scaleY || 1,
                angle: obj.angle || 0,
                fill: obj.fill,
                stroke: obj.stroke,
                strokeWidth: obj.strokeWidth,
                radius: obj.radius,
                text: obj.text,
                fontSize: obj.fontSize,
                fontFamily: obj.fontFamily,
                playerType: obj.playerType,
                width: obj.width,
                height: obj.height
            }));
    }

    // Keep existing notification function
    function showNotification(message, type = 'success') {
        const notification = document.createElement('div');
        notification.className = `alert alert-${type} position-fixed top-0 end-0 m-3`;
        notification.style.zIndex = '9999';
        notification.textContent = message;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 3000);
    }

    // Keep all other existing functions (addPlayer, addDisc, etc.)
    // ... (keep all other existing functions)
});
