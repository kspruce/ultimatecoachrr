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
        // Add a basic ultimate field (you can replace with an actual field image)
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
        // Play/pause button
        document.getElementById('play-pause').addEventListener('click', togglePlayPause);
        
        // Previous frame button
        document.getElementById('prev-frame').addEventListener('click', showPreviousFrame);
        
        // Next frame button
        document.getElementById('next-frame').addEventListener('click', showNextFrame);
        
        // Speed control
        document.getElementById('speed-control').addEventListener('change', function() {
            playbackSpeed = parseFloat(this.value);
            
            // If currently playing, restart with new speed
            if (isPlaying) {
                stopPlayback();
                startPlayback();
            }
        });
    }
    
    function togglePlayPause() {
        if (isPlaying) {
            stopPlayback();
        } else {
            startPlayback();
        }
    }
    
    function startPlayback() {
        if (frames.length <= 1) return;
        
        isPlaying = true;
        document.getElementById('play-pause').innerHTML = '<i class="fas fa-pause"></i>';
        
        // Calculate interval based on speed (1.5 seconds per frame at 1x speed)
        const interval = 1500 / playbackSpeed;
        
        playInterval = setInterval(() => {
            currentFrameIndex = (currentFrameIndex + 1) % frames.length;
            showFrame(currentFrameIndex);
        }, interval);
    }
    
    function stopPlayback() {
        isPlaying = false;
        document.getElementById('play-pause').innerHTML = '<i class="fas fa-play"></i>';
        
        if (playInterval) {
            clearInterval(playInterval);
            playInterval = null;
        }
    }
    
    function showPreviousFrame() {
        if (frames.length <= 1) return;
        
        // Stop playback if it's running
        if (isPlaying) {
            stopPlayback();
        }
        
        currentFrameIndex = (currentFrameIndex - 1 + frames.length) % frames.length;
        showFrame(currentFrameIndex);
    }
    
    function showNextFrame() {
        if (frames.length <= 1) return;
        
        // Stop playback if it's running
        if (isPlaying) {
            stopPlayback();
        }
        
        currentFrameIndex = (currentFrameIndex + 1) % frames.length;
        showFrame(currentFrameIndex);
    }
    
    function showFrame(frameIndex) {
        if (frameIndex < 0 || frameIndex >= frames.length) return;
        
        // Clear canvas except for field
        clearCanvas();
        
        // Load frame elements
        loadFrameElements(frames[frameIndex].elements);
        
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
            } else if (el.type === 'path') {
                // Handle paths (drawn lines)
                const path = new fabric.Path(el.path, {
                    left: el.left,
                    top: el.top,
                    stroke: el.stroke || '#000000',
                    strokeWidth: el.strokeWidth || 2,
                    fill: '',
                    scaleX: el.scaleX || 1,
                    scaleY: el.scaleY || 1,
                    angle: el.angle || 0,
                    selectable: false,
                    evented: false
                });
                
                canvas.add(path);
            }
        });
        
        canvas.renderAll();
    }
    
    function loadDrillData(drillId) {
        // Fetch drill details and frames
        fetch(`/drills/api/drills/${drillId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Failed to load drill');
                }
                return response.json();
            })
            .then(data => {
                // Load frames
                if (data.frames && data.frames.length > 0) {
                    frames = data.frames.map(frame => ({
                        id: frame.id,
                        name: frame.name,
                        elements: frame.elements,
                        sequence: frame.sequence
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
                alert('Failed to load drill data');
            });
    }
});
