document.addEventListener('DOMContentLoaded', function() {
    // Initialize variables
    let canvas;
    let frames = [];
    let currentFrameIndex = 0;
    let isPlaying = false;
    let playInterval = null;
    let playbackSpeed = 1;
    
    // Get drill ID
    const drillId = document.getElementById('drill-data').dataset.drillId;
    
    // Initialize the canvas with Fabric.js
    initCanvas();
    
    // Load drill data
    loadDrillData(drillId);
    
    // Set up event listeners
    setupEventListeners();
    
    function initCanvas() {
        // Create a Fabric.js canvas
        canvas = new fabric.Canvas('drill-canvas', {
            width: document.querySelector('.canvas-container').offsetWidth,
            height: document.querySelector('.canvas-container').offsetHeight,
            backgroundColor: '#ffffff',
            selection: false,
            interactive: false // View only mode
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
        // Keep existing field background code
        // ... (keep existing field background code)
    }
    
    function setupEventListeners() {
        // Keep existing event listener setup
        // ... (keep existing event listener code)
    }

    function loadDrillData(drillId) {
        fetch(`/drills/api/drills/${drillId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Failed to load drill');
                }
                return response.json();
            })
            .then(data => {
                // Load main diagram from S3 if available
                if (data.diagram_url) {
                    loadDiagramFromS3(data.diagram_url);
                }

                // Load frames
                if (data.frames && data.frames.length > 0) {
                    frames = data.frames.map(frame => ({
                        id: frame.id,
                        name: frame.name,
                        elements: frame.elements,
                        sequence: frame.sequence,
                        diagram_url: frame.diagram_url // S3 URL for frame diagram
                    }));
                    
                    // Sort frames by sequence
                    frames.sort((a, b) => a.sequence - b.sequence);
                    
                    // Update total frames count
                    document.getElementById('total-frames').textContent = frames.length;
                    
                    // Show the first frame
                    showFrame(0);
                } else {
                    // No frames, show empty state
                    document.getElementById('total-frames').textContent = '0';
                    document.getElementById('current-frame-num').textContent = '0';
                }
            })
            .catch(error => {
                console.error('Error loading drill:', error);
                showNotification('Failed to load drill data', 'error');
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

    function showFrame(frameIndex) {
        if (frameIndex < 0 || frameIndex >= frames.length) return;
        
        // Clear canvas except for field
        clearCanvas();
        
        const frame = frames[frameIndex];

        // Load frame diagram from S3 if available
        if (frame.diagram_url) {
            loadDiagramFromS3(frame.diagram_url);
        }
        
        // Load frame elements
        loadFrameElements(frame.elements);
        
        // Update frame counter
        document.getElementById('current-frame-num').textContent = frameIndex + 1;
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
    
    function loadFrameElements(elements) {
        if (!elements || !Array.isArray(elements)) return;
        
        elements.forEach(el => {
            if (el.type === 'player') {
                const circle = new fabric.Circle({
                    radius: el.radius || 15,
                    fill: el.fill,
                    stroke: el.stroke,
                    strokeWidth: el.strokeWidth
                });
                
                const text = new fabric.Text(el.playerType === 'offense' ? 'O' : 'D', {
                    fontSize: el.fontSize || 16,
                    fontFamily: el.fontFamily || 'Arial',
                    fill: '#ffffff'
                });
                
                const player = new fabric.Group([circle, text], {
                    left: el.left,
                    top: el.top,
                    scaleX: el.scaleX || 1,
                    scaleY: el.scaleY || 1,
                    angle: el.angle || 0,
                    selectable: false,
                    evented: false
                });
                
                canvas.add(player);
            } else if (el.type === 'disc') {
                const disc = new fabric.Circle({
                    left: el.left,
                    top: el.top,
                    radius: el.radius || 10,
                    fill: el.fill || '#ffffff',
                    stroke: el.stroke || '#000000',
                    strokeWidth: el.strokeWidth || 2,
                    scaleX: el.scaleX || 1,
                    scaleY: el.scaleY || 1,
                    angle: el.angle || 0,
                    selectable: false,
                    evented: false
                });
                
                canvas.add(disc);
            } else if (el.type === 'text') {
                const text = new fabric.Text(el.text || 'Text', {
                    left: el.left,
                    top: el.top,
                    fontSize: el.fontSize || 20,
                    fontFamily: el.fontFamily || 'Arial',
                    fill: el.fill || '#000000',
                    scaleX: el.scaleX || 1,
                    scaleY: el.scaleY || 1,
                    angle: el.angle || 0,
                    selectable: false,
                    evented: false
                });
                
                canvas.add(text);
            }
        });
        
        canvas.renderAll();
    }

    function showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `alert alert-${type} position-fixed top-0 end-0 m-3`;
        notification.style.zIndex = '9999';
        notification.textContent = message;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 3000);
    }

    // Keep existing playback control functions
    function togglePlayPause() {
        if (isPlaying) {
            stopPlayback();
        } else {
            startPlayback();
        }
    }
    
    function startPlayback() {
        // Keep existing playback code
        // ... (keep existing playback code)
    }
    
    function stopPlayback() {
        // Keep existing stop code
        // ... (keep existing stop code)
    }
    
    function showPreviousFrame() {
        // Keep existing previous frame code
        // ... (keep existing previous frame code)
    }
    
    function showNextFrame() {
        // Keep existing next frame code
        // ... (keep existing next frame code)
    }
});
