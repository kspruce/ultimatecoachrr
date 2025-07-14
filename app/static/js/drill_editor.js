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
        const fieldWidth = canvas.width;
        const fieldHeight = canvas.height;

        // Create field rectangle
        const field = new fabric.Rect({
            width: fieldWidth * 0.9,
            height: fieldHeight * 0.8,
            left: fieldWidth * 0.05,
            top: fieldHeight * 0.1,
            fill: '#88cc88',
            stroke: 'white',
            strokeWidth: 2,
            selectable: false,
            evented: false
        });

        // Create endzones
        const endzone1 = new fabric.Rect({
            width: fieldWidth * 0.9,
            height: fieldHeight * 0.15,
            left: fieldWidth * 0.05,
            top: fieldHeight * 0.1,
            fill: '#77bb77',
            stroke: 'white',
            strokeWidth: 2,
            selectable: false,
            evented: false
        });

        const endzone2 = new fabric.Rect({
            width: fieldWidth * 0.9,
            height: fieldHeight * 0.15,
            left: fieldWidth * 0.05,
            top: fieldHeight * 0.75,
            fill: '#77bb77',
            stroke: 'white',
            strokeWidth: 2,
            selectable: false,
            evented: false
        });

        // Add field elements to canvas
        canvas.add(field, endzone1, endzone2);

        // Send to back and make them background
        field.sendToBack();
        endzone1.sendToBack();
        endzone2.sendToBack();

        canvas.renderAll();
    }

    function setupEventListeners() {
        // Tool selection
        document.querySelectorAll('.tool-btn[data-tool]').forEach(btn => {
            btn.addEventListener('click', function() {
                const tool = this.dataset.tool;
                setActiveTool(tool);
            });
        });

        // Canvas actions
        document.querySelectorAll('.tool-btn[data-action]').forEach(btn => {
            btn.addEventListener('click', function() {
                const action = this.dataset.action;
                handleAction(action);
            });
        });

        // Canvas click for adding elements
        canvas.on('mouse:down', function(options) {
            handleCanvasClick(options);
        });

        // Save drill button
        document.getElementById('save-drill').addEventListener('click', saveDrill);

        // Field settings
        document.getElementById('apply-field-settings').addEventListener('click', applyFieldSettings);

        // Keyboard shortcuts
        document.addEventListener('keydown', handleKeyboardShortcuts);
    }

    function setActiveTool(tool) {
        // Remove active class from all tools
        document.querySelectorAll('.tool-btn[data-tool]').forEach(btn => {
            btn.classList.remove('active');
        });

        // Add active class to selected tool
        document.querySelector(`.tool-btn[data-tool="${tool}"]`).classList.add('active');

        // Set current tool
        currentTool = tool;

        // Update canvas mode based on tool
        if (tool === 'select') {
            canvas.isDrawingMode = false;
            canvas.selection = true;
        } else if (tool === 'path') {
            canvas.isDrawingMode = true;
            canvas.freeDrawingBrush.width = 2;
            canvas.freeDrawingBrush.color = '#000000';
            canvas.selection = false;
        } else {
            canvas.isDrawingMode = false;
            canvas.selection = false;
        }
    }

    function handleAction(action) {
        if (action === 'delete') {
            deleteSelectedObjects();
        } else if (action === 'clear') {
            clearCanvas();
        }
    }

    function handleCanvasClick(options) {
        if (canvas.isDrawingMode) return;

        const pointer = canvas.getPointer(options.e);

        switch (currentTool) {
            case 'player-o':
                addPlayer(pointer.x, pointer.y, 'offense');
                break;
            case 'player-d':
                addPlayer(pointer.x, pointer.y, 'defense');
                break;
            case 'disc':
                addDisc(pointer.x, pointer.y);
                break;
            case 'cone':
                addCone(pointer.x, pointer.y);
                break;
            case 'text':
                addText(pointer.x, pointer.y);
                break;
        }
    }


    // Object Creation Functions
    function addPlayer(x, y, type) {
        const color = type === 'offense' ? '#ff6666' : '#6666ff';
        const label = type === 'offense' ? 'O' : 'D';

        const circle = new fabric.Circle({
            radius: 15,
            fill: color,
            stroke: '#000000',
            strokeWidth: 2,
            originX: 'center',
            originY: 'center'
        });

        const text = new fabric.Text(label, {
            fontSize: 16,
            fontFamily: 'Arial',
            fill: '#ffffff',
            originX: 'center',
            originY: 'center'
        });

        const player = new fabric.Group([circle, text], {
            left: x - 15,
            top: y - 15,
            type: 'player',
            playerType: type
        });

        canvas.add(player);
        canvas.setActiveObject(player);
        canvas.renderAll();
    }

    function addDisc(x, y) {
        const disc = new fabric.Circle({
            left: x - 10,
            top: y - 10,
            radius: 10,
            fill: '#ffffff',
            stroke: '#000000',
            strokeWidth: 2,
            type: 'disc'
        });

        canvas.add(disc);
        canvas.setActiveObject(disc);
        canvas.renderAll();
    }

    function addCone(x, y) {
        const cone = new fabric.Triangle({
            left: x - 10,
            top: y - 15,
            width: 20,
            height: 30,
            fill: '#ffa500',
            stroke: '#000000',
            strokeWidth: 1,
            type: 'cone'
        });

        canvas.add(cone);
        canvas.setActiveObject(cone);
        canvas.renderAll();
    }

    function addText(x, y) {
        const text = new fabric.IText('Text', {
            left: x,
            top: y,
            fontSize: 20,
            fontFamily: 'Arial',
            fill: '#000000',
            type: 'text'
        });

        canvas.add(text);
        canvas.setActiveObject(text);
        canvas.renderAll();

        // Enter edit mode immediately
        text.enterEditing();
    }

    // Canvas Manipulation Functions
    function deleteSelectedObjects() {
        const activeObjects = canvas.getActiveObjects();

        if (activeObjects.length > 0) {
            canvas.discardActiveObject();

            activeObjects.forEach(obj => {
                canvas.remove(obj);
            });

            canvas.renderAll();
        }
    }

    function clearCanvas() {
        // Keep only the field background
        const objects = canvas.getObjects();
        const toRemove = objects.filter(obj => {
            return obj.type !== 'rect'; // Assuming field elements are rectangles
        });

        toRemove.forEach(obj => {
            canvas.remove(obj);
        });

        canvas.renderAll();
    }

    // Save/Load Functions
    function saveDrill() {
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
            diagram: canvas.toDataURL({
                format: 'png',
                quality: 1
            }),
            elements: getCurrentCanvasState()
        };

        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        if (!csrfToken) {
            showNotification('Security token not found. Please refresh the page.', 'error');
            return;
        }

        const url = drillId ? 
            `/drills/api/drills/${drillId}` : 
            '/drills/api/drills';

        const method = drillId ? 'PUT' : 'POST';

        fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(drillData)
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
    }

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

    function loadElements(elements) {
        elements.forEach(el => {
            switch (el.type) {
                case 'player':
                    addPlayer(el.left + 15, el.top + 15, el.playerType);
                    break;
                case 'disc':
                    addDisc(el.left + 10, el.top + 10);
                    break;
                case 'cone':
                    addCone(el.left + 10, el.top + 15);
                    break;
                case 'text':
                    const text = new fabric.Text(el.text, {
                        left: el.left,
                        top: el.top,
                        fontSize: el.fontSize,
                        fontFamily: el.fontFamily,
                        fill: el.fill,
                        type: 'text'
                    });
                    canvas.add(text);
                    break;
            }
        });
        canvas.renderAll();
    }

    // Field Settings Functions
    function applyFieldSettings() {
        const length = document.getElementById('field-length').value;
        const width = document.getElementById('field-width').value;
        const endzoneDepth = document.getElementById('endzone-depth').value;
        const showGrid = document.getElementById('show-grid').checked;

        // Update field display
        updateField(length, width, endzoneDepth, showGrid);

        // Close modal
        bootstrap.Modal.getInstance(document.getElementById('fieldSettingsModal')).hide();
    }

    function updateField(length, width, endzoneDepth, showGrid) {
        // Implementation of field updating logic
        // This would update the field dimensions and appearance
        // You'll need to implement this based on your specific needs
    }

    // Notification Function
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

    // Keyboard Shortcuts
    function handleKeyboardShortcuts(e) {
        // Don't trigger shortcuts when typing in input fields
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        switch (e.key.toLowerCase()) {
            case 'v':
                setActiveTool('select');
                break;
            case 'o':
                setActiveTool('player-o');
                break;
            case 'd':
                setActiveTool('player-d');
                break;
            case 'f':
                setActiveTool('disc');
                break;
            case 'c':
                setActiveTool('cone');
                break;
            case 'p':
                setActiveTool('path');
                break;
            case 't':
                setActiveTool('text');
                break;
            case 'Delete':
                deleteSelectedObjects();
                break;
            case 's':
                if (e.ctrlKey) {
                    e.preventDefault();
                    saveDrill();
                }
                break;
        }
    }
});
