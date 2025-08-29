/**
 * Simplified Stats Storage JavaScript
 * This is a simplified version to help troubleshoot button click issues
 */

// Log when the script loads
console.log("Stats storage script loaded");

document.addEventListener('DOMContentLoaded', function() {
    console.log("DOM loaded, looking for save button");
    
    // Find the save button
    const saveStatsBtn = document.getElementById('saveStatsBtn');
    console.log("Save button found:", saveStatsBtn);
    
    if (saveStatsBtn) {
        console.log("Adding click event listener to save button");
        
        // Add click event listener
        saveStatsBtn.addEventListener('click', function() {
            console.log("Save button clicked!");
            alert("Save button clicked! Now attempting to save stats...");
            
            // Determine which page we're on
            const currentPath = window.location.pathname;
            console.log("Current path:", currentPath);
            
            // Simple data to save
            const statsData = {
                test: 'data',
                timestamp: new Date().toISOString()
            };
            
            // Get CSRF token if available
            let csrfToken = '';
            const csrfElement = document.querySelector('meta[name="csrf-token"]');
            if (csrfElement) {
                csrfToken = csrfElement.getAttribute('content');
                console.log("CSRF token found");
            } else {
                console.log("No CSRF token found");
            }
            
            // Determine endpoint based on path
            let endpoint = '/api/stats/save/index';
            if (currentPath.includes('/team_stats')) {
                endpoint = '/api/stats/save/team';
            } else if (currentPath.includes('/game_stats')) {
                const gameId = new URLSearchParams(window.location.search).get('game_id');
                if (gameId) {
                    endpoint = `/api/stats/save/game/${gameId}`;
                } else {
                    alert("Error: Could not determine game ID");
                    return;
                }
            } else if (currentPath.includes('/player_stats')) {
                const playerId = new URLSearchParams(window.location.search).get('player_id');
                if (playerId) {
                    endpoint = `/api/stats/save/player/${playerId}`;
                } else {
                    alert("Error: Could not determine player ID");
                    return;
                }
            }
            
            console.log("Using endpoint:", endpoint);
            
            // Show loading state
            saveStatsBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...';
            saveStatsBtn.disabled = true;
            
            // Send request
            fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    stats_data: statsData,
                    filter_params: {},
                    version: 1
                })
            })
            .then(response => {
                console.log("Response status:", response.status);
                return response.json();
            })
            .then(data => {
                console.log("Response data:", data);
                if (data.error) {
                    alert('Error: ' + data.error);
                } else {
                    alert('Stats saved successfully!');
                }
            })
            .catch(error => {
                console.error('Error saving stats:', error);
                alert('Error saving stats: ' + error.message);
            })
            .finally(() => {
                // Restore button state
                saveStatsBtn.innerHTML = '<i class="bi bi-save"></i> Save Stats to Database';
                saveStatsBtn.disabled = false;
            });
        });
        
        // Also add a direct click handler as a backup
        saveStatsBtn.onclick = function() {
            console.log("Button clicked via onclick handler");
        };
    } else {
        console.log("Save button not found on the page");
    }
    
    // Add a test function that can be called from the console
    window.testSaveStats = function() {
        console.log("Running test save function");
        alert("Testing save stats function");
        
        fetch('/api/stats/save/index', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
            },
            body: JSON.stringify({
                stats_data: { test: 'data' },
                filter_params: {},
                version: 1
            })
        })
        .then(response => response.json())
        .then(data => {
            console.log('Success:', data);
            alert('Stats saved successfully!');
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error saving stats: ' + error);
        });
    };
});