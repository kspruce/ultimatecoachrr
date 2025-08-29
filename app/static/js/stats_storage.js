/**
 * Stats Storage JavaScript
 * Handles saving and retrieving stats to/from the database
 */

document.addEventListener('DOMContentLoaded', function() {
    // Check if we're on a stats page with a save button
    const saveStatsBtn = document.getElementById('saveStatsBtn');
    if (saveStatsBtn) {
        // Check if user is admin and show/hide button accordingly
        if (!isUserAdmin()) {
            saveStatsBtn.style.display = 'none';
        } else {
            saveStatsBtn.addEventListener('click', function() {
                // Determine which page we're on
                const currentPath = window.location.pathname;
                
                if (currentPath.includes('/stats')) {
                    if (currentPath.endsWith('/stats')) {
                        // Index stats page
                        saveIndexStats();
                    } else if (currentPath.includes('/team_stats')) {
                        // Team stats page
                        saveTeamStats();
                    } else if (currentPath.includes('/game_stats')) {
                        // Game stats page
                        const gameId = getGameIdFromUrl();
                        if (gameId) {
                            saveGameStats(gameId);
                        } else {
                            showNotification('Error: Could not determine game ID', 'danger');
                        }
                    } else if (currentPath.includes('/player_stats')) {
                        // Player stats page
                        const playerId = getPlayerIdFromUrl();
                        if (playerId) {
                            savePlayerStats(playerId);
                        } else {
                            showNotification('Error: Could not determine player ID', 'danger');
                        }
                    }
                }
            });
        }
    }
    
    // Add link to stats management page for admins
    if (isUserAdmin()) {
        addStatsManagementLink();
    }
    
    // Check if we should load saved stats
    checkForSavedStats();
});

/**
 * Check if the current user is an admin
 */
function isUserAdmin() {
    // This function should be implemented based on your app's authentication system
    // For now, we'll assume the user is an admin if the save button is present
    return document.getElementById('saveStatsBtn') !== null;
}

/**
 * Add a link to the stats management page
 */
function addStatsManagementLink() {
    // Find a good place to add the link
    const saveStatsBtn = document.getElementById('saveStatsBtn');
    if (saveStatsBtn) {
        const parentElement = saveStatsBtn.parentElement;
        
        // Create the link
        const managementLink = document.createElement('a');
        managementLink.href = '/stats/manage';
        managementLink.className = 'btn btn-outline-secondary ms-2';
        managementLink.innerHTML = '<i class="bi bi-gear"></i> Manage Stats';
        
        // Add the link
        parentElement.appendChild(managementLink);
    }
}

/**
 * Extract game ID from URL
 */
function getGameIdFromUrl() {
    const urlParams = new URLSearchParams(window.location.search);
    const gameId = urlParams.get('game_id');
    return gameId;
}

/**
 * Extract player ID from URL
 */
function getPlayerIdFromUrl() {
    const urlParams = new URLSearchParams(window.location.search);
    const playerId = urlParams.get('player_id');
    return playerId;
}

/**
 * Save index page stats to database
 */
function saveIndexStats() {
    // Show save options modal
    showSaveOptionsModal('index', function(options) {
        // Show loading state
        const saveBtn = document.getElementById('saveStatsBtn');
        const originalText = saveBtn.innerHTML;
        saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...';
        saveBtn.disabled = true;
        
        // Collect all stats data from the page
        const statsData = collectIndexStatsData();
        
        // Get filter parameters if any
        const filterParams = collectFilterParams();
        
        // Send data to server
        fetch('/api/stats/save/index', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                stats_data: statsData,
                filter_params: filterParams,
                version: options.version,
                create_new_version: options.createNewVersion
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showNotification('Error: ' + data.error, 'danger');
            } else {
                showNotification('Stats saved successfully!', 'success');
            }
        })
        .catch(error => {
            console.error('Error saving stats:', error);
            showNotification('Error saving stats: ' + error.message, 'danger');
        })
        .finally(() => {
            // Restore button state
            saveBtn.innerHTML = originalText;
            saveBtn.disabled = false;
        });
    });
}

/**
 * Save team stats to database
 */
function saveTeamStats() {
    // Show save options modal
    showSaveOptionsModal('team', function(options) {
        // Show loading state
        const saveBtn = document.getElementById('saveStatsBtn');
        const originalText = saveBtn.innerHTML;
        saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...';
        saveBtn.disabled = true;
        
        // Collect all stats data from the page
        const statsData = collectTeamStatsData();
        
        // Get filter parameters if any
        const filterParams = collectFilterParams();
        
        // Send data to server
        fetch('/api/stats/save/team', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                stats_data: statsData,
                filter_params: filterParams,
                version: options.version,
                create_new_version: options.createNewVersion
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showNotification('Error: ' + data.error, 'danger');
            } else {
                showNotification('Team stats saved successfully!', 'success');
            }
        })
        .catch(error => {
            console.error('Error saving team stats:', error);
            showNotification('Error saving team stats: ' + error.message, 'danger');
        })
        .finally(() => {
            // Restore button state
            saveBtn.innerHTML = originalText;
            saveBtn.disabled = false;
        });
    });
}

/**
 * Save game stats to database
 */
function saveGameStats(gameId) {
    // Show save options modal
    showSaveOptionsModal('game', function(options) {
        // Show loading state
        const saveBtn = document.getElementById('saveStatsBtn');
        const originalText = saveBtn.innerHTML;
        saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...';
        saveBtn.disabled = true;
        
        // Collect all stats data from the page
        const statsData = collectGameStatsData();
        
        // Get filter parameters if any
        const filterParams = collectFilterParams();
        
        // Send data to server
        fetch(`/api/stats/save/game/${gameId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                stats_data: statsData,
                filter_params: filterParams,
                version: options.version,
                create_new_version: options.createNewVersion
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showNotification('Error: ' + data.error, 'danger');
            } else {
                showNotification('Game stats saved successfully!', 'success');
            }
        })
        .catch(error => {
            console.error('Error saving game stats:', error);
            showNotification('Error saving game stats: ' + error.message, 'danger');
        })
        .finally(() => {
            // Restore button state
            saveBtn.innerHTML = originalText;
            saveBtn.disabled = false;
        });
    });
}

/**
 * Save player stats to database
 */
function savePlayerStats(playerId) {
    // Show save options modal
    showSaveOptionsModal('player', function(options) {
        // Show loading state
        const saveBtn = document.getElementById('saveStatsBtn');
        const originalText = saveBtn.innerHTML;
        saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...';
        saveBtn.disabled = true;
        
        // Collect all stats data from the page
        const statsData = collectPlayerStatsData();
        
        // Get filter parameters if any
        const filterParams = collectFilterParams();
        
        // Get game ID if we're viewing player stats for a specific game
        const gameId = getGameIdFromUrl();
        
        // Send data to server
        fetch(`/api/stats/save/player/${playerId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({
                stats_data: statsData,
                filter_params: filterParams,
                game_id: gameId,
                version: options.version,
                create_new_version: options.createNewVersion
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                showNotification('Error: ' + data.error, 'danger');
            } else {
                showNotification('Player stats saved successfully!', 'success');
            }
        })
        .catch(error => {
            console.error('Error saving player stats:', error);
            showNotification('Error saving player stats: ' + error.message, 'danger');
        })
        .finally(() => {
            // Restore button state
            saveBtn.innerHTML = originalText;
            saveBtn.disabled = false;
        });
    });
}

/**
 * Show modal with save options
 */
function showSaveOptionsModal(statsType, callback) {
    // Create modal if it doesn't exist
    let modal = document.getElementById('saveOptionsModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'saveOptionsModal';
        modal.className = 'modal fade';
        modal.tabIndex = '-1';
        modal.setAttribute('aria-labelledby', 'saveOptionsModalLabel');
        modal.setAttribute('aria-hidden', 'true');
        
        modal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title" id="saveOptionsModalLabel">Save Options</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        <div class="mb-3">
                            <label for="versionInput" class="form-label">Version</label>
                            <input type="number" class="form-control" id="versionInput" value="1" min="1">
                            <div class="form-text">Specify a version number for these stats.</div>
                        </div>
                        <div class="mb-3 form-check">
                            <input type="checkbox" class="form-check-input" id="createNewVersionCheck">
                            <label class="form-check-label" for="createNewVersionCheck">Create as new version</label>
                            <div class="form-text">If checked, this will create a new version instead of updating an existing one.</div>
                        </div>
                        <div class="mb-3 form-check">
                            <input type="checkbox" class="form-check-input" id="compressDataCheck">
                            <label class="form-check-label" for="compressDataCheck">Compress data</label>
                            <div class="form-text">If checked, the data will be compressed to save storage space.</div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-primary" id="confirmSaveBtn">Save Stats</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
    }
    
    // Get the current version for this stats type
    checkCurrentVersion(statsType, function(currentVersion) {
        // Set the default version
        const versionInput = document.getElementById('versionInput');
        versionInput.value = currentVersion + 1;
        
        // Show the modal
        const modalInstance = new bootstrap.Modal(modal);
        modalInstance.show();
        
        // Handle save button click
        const confirmSaveBtn = document.getElementById('confirmSaveBtn');
        const handleSave = function() {
            const version = parseInt(document.getElementById('versionInput').value) || 1;
            const createNewVersion = document.getElementById('createNewVersionCheck').checked;
            const compressData = document.getElementById('compressDataCheck').checked;
            
            modalInstance.hide();
            confirmSaveBtn.removeEventListener('click', handleSave);
            
            callback({
                version: version,
                createNewVersion: createNewVersion,
                compressData: compressData
            });
        };
        
        confirmSaveBtn.addEventListener('click', handleSave);
    });
}

/**
 * Check the current version for a stats type
 */
function checkCurrentVersion(statsType, callback) {
    let url = '';
    let params = new URLSearchParams();
    
    // Build the URL based on stats type
    switch (statsType) {
        case 'index':
            url = '/api/stats/check/index';
            break;
        case 'team':
            url = '/api/stats/check/team';
            break;
        case 'game':
            url = '/api/stats/check/game/' + getGameIdFromUrl();
            break;
        case 'player':
            url = '/api/stats/check/player/' + getPlayerIdFromUrl();
            if (getGameIdFromUrl()) {
                params.append('game_id', getGameIdFromUrl());
            }
            break;
    }
    
    // Add filter parameters if any
    const filterParams = collectFilterParams();
    if (filterParams) {
        params.append('filter_params', JSON.stringify(filterParams));
    }
    
    // Add params to URL
    if (params.toString()) {
        url += '?' + params.toString();
    }
    
    // Check if stats exist
    fetch(url, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.exists) {
            callback(data.version || 1);
        } else {
            callback(0);
        }
    })
    .catch(error => {
        console.error('Error checking current version:', error);
        callback(0);
    });
}

/**
 * Check if there are saved stats for the current page
 */
function checkForSavedStats() {
    const currentPath = window.location.pathname;
    
    if (currentPath.includes('/stats')) {
        if (currentPath.endsWith('/stats')) {
            // Index stats page
            checkIndexStats();
        } else if (currentPath.includes('/team_stats')) {
            // Team stats page
            checkTeamStats();
        } else if (currentPath.includes('/game_stats')) {
            // Game stats page
            const gameId = getGameIdFromUrl();
            if (gameId) {
                checkGameStats(gameId);
            }
        } else if (currentPath.includes('/player_stats')) {
            // Player stats page
            const playerId = getPlayerIdFromUrl();
            if (playerId) {
                checkPlayerStats(playerId);
            }
        }
    }
}

/**
 * Check if index stats are saved
 */
function checkIndexStats() {
    // Get filter parameters if any
    const filterParams = collectFilterParams();
    
    // Build query string
    let queryString = '';
    if (filterParams) {
        queryString = `?filter_params=${encodeURIComponent(JSON.stringify(filterParams))}`;
    }
    
    // Check if stats exist
    fetch(`/api/stats/check/index${queryString}`, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.exists) {
            // Show notification that we're using saved stats
            showNotification(`Using saved stats v${data.version} from ${formatDate(data.updated_at)}`, 'info', 10000);
            
            // Update the save button to show "Update Stats"
            updateSaveButton(`Update Stats (v${data.version})`);
            
            // Optionally, use the saved stats data instead of calculating again
            // This would require modifying the page's existing JavaScript
        }
    })
    .catch(error => {
        console.error('Error checking for saved stats:', error);
    });
}

/**
 * Check if team stats are saved
 */
function checkTeamStats() {
    // Get filter parameters if any
    const filterParams = collectFilterParams();
    
    // Build query string
    let queryString = '';
    if (filterParams) {
        queryString = `?filter_params=${encodeURIComponent(JSON.stringify(filterParams))}`;
    }
    
    // Check if stats exist
    fetch(`/api/stats/check/team${queryString}`, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.exists) {
            // Show notification that we're using saved stats
            showNotification(`Using saved stats v${data.version} from ${formatDate(data.updated_at)}`, 'info', 10000);
            
            // Update the save button to show "Update Stats"
            updateSaveButton(`Update Stats (v${data.version})`);
            
            // Optionally, use the saved stats data instead of calculating again
        }
    })
    .catch(error => {
        console.error('Error checking for saved team stats:', error);
    });
}

/**
 * Check if game stats are saved
 */
function checkGameStats(gameId) {
    // Get filter parameters if any
    const filterParams = collectFilterParams();
    
    // Build query string
    let queryString = '';
    if (filterParams) {
        queryString = `?filter_params=${encodeURIComponent(JSON.stringify(filterParams))}`;
    }
    
    // Check if stats exist
    fetch(`/api/stats/check/game/${gameId}${queryString}`, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.exists) {
            // Show notification that we're using saved stats
            showNotification(`Using saved stats v${data.version} from ${formatDate(data.updated_at)}`, 'info', 10000);
            
            // Update the save button to show "Update Stats"
            updateSaveButton(`Update Stats (v${data.version})`);
            
            // Optionally, use the saved stats data instead of calculating again
        }
    })
    .catch(error => {
        console.error('Error checking for saved game stats:', error);
    });
}

/**
 * Check if player stats are saved
 */
function checkPlayerStats(playerId) {
    // Get filter parameters if any
    const filterParams = collectFilterParams();
    
    // Get game ID if we're viewing player stats for a specific game
    const gameId = getGameIdFromUrl();
    
    // Build query string
    let queryString = '';
    if (filterParams) {
        queryString = `?filter_params=${encodeURIComponent(JSON.stringify(filterParams))}`;
    }
    if (gameId) {
        queryString += queryString ? `&game_id=${gameId}` : `?game_id=${gameId}`;
    }
    
    // Check if stats exist
    fetch(`/api/stats/check/player/${playerId}${queryString}`, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.exists) {
            // Show notification that we're using saved stats
            showNotification(`Using saved stats v${data.version} from ${formatDate(data.updated_at)}`, 'info', 10000);
            
            // Update the save button to show "Update Stats"
            updateSaveButton(`Update Stats (v${data.version})`);
            
            // Optionally, use the saved stats data instead of calculating again
        }
    })
    .catch(error => {
        console.error('Error checking for saved player stats:', error);
    });
}

/**
 * Collect index stats data from the page
 */
function collectIndexStatsData() {
    const statsData = {};
    
    // Collect stats from stat cards
    document.querySelectorAll('.stat-card').forEach(card => {
        const statLabel = card.querySelector('.stat-label')?.textContent.trim();
        const statValue = card.querySelector('.stat-value')?.textContent.trim();
        
        if (statLabel && statValue) {
            statsData[statLabel] = statValue;
        }
    });
    
    // Collect data from tables
    document.querySelectorAll('table').forEach((table, index) => {
        const tableId = table.id || `table_${index}`;
        statsData[tableId] = collectTableData(table);
    });
    
    // Collect data from charts
    // This is more complex and depends on how charts are implemented
    // For now, we'll just collect chart container IDs
    document.querySelectorAll('.chart-container').forEach((chart, index) => {
        const chartId = chart.id || `chart_${index}`;
        statsData[`chart_${chartId}`] = { id: chartId };
    });
    
    return optimizeStatsData(statsData);
}

/**
 * Collect team stats data from the page
 */
function collectTeamStatsData() {
    const statsData = {};
    
    // Collect stats from stat cards
    document.querySelectorAll('.stat-card').forEach(card => {
        const statLabel = card.querySelector('.stat-label')?.textContent.trim();
        const statValue = card.querySelector('.stat-value')?.textContent.trim();
        
        if (statLabel && statValue) {
            statsData[statLabel] = statValue;
        }
    });
    
    // Collect data from tables
    document.querySelectorAll('table').forEach((table, index) => {
        const tableId = table.id || `table_${index}`;
        statsData[tableId] = collectTableData(table);
    });
    
    // Collect data from charts
    document.querySelectorAll('.chart-container').forEach((chart, index) => {
        const chartId = chart.id || `chart_${index}`;
        statsData[`chart_${chartId}`] = { id: chartId };
    });
    
    return optimizeStatsData(statsData);
}

/**
 * Collect game stats data from the page
 */
function collectGameStatsData() {
    const statsData = {};
    
    // Collect game info
    const gameTitle = document.querySelector('h1')?.textContent.trim();
    if (gameTitle) {
        statsData.gameTitle = gameTitle;
    }
    
    // Collect stats from stat cards
    document.querySelectorAll('.stat-card').forEach(card => {
        const statLabel = card.querySelector('.stat-label')?.textContent.trim();
        const statValue = card.querySelector('.stat-value')?.textContent.trim();
        
        if (statLabel && statValue) {
            statsData[statLabel] = statValue;
        }
    });
    
    // Collect data from tables
    document.querySelectorAll('table').forEach((table, index) => {
        const tableId = table.id || `table_${index}`;
        statsData[tableId] = collectTableData(table);
    });
    
    // Collect data from charts
    document.querySelectorAll('.chart-container').forEach((chart, index) => {
        const chartId = chart.id || `chart_${index}`;
        statsData[`chart_${chartId}`] = { id: chartId };
    });
    
    return optimizeStatsData(statsData);
}

/**
 * Collect player stats data from the page
 */
function collectPlayerStatsData() {
    const statsData = {};
    
    // Collect player info
    const playerName = document.querySelector('h1')?.textContent.trim();
    if (playerName) {
        statsData.playerName = playerName;
    }
    
    // Collect stats from stat cards
    document.querySelectorAll('.stat-card').forEach(card => {
        const statLabel = card.querySelector('.stat-label')?.textContent.trim();
        const statValue = card.querySelector('.stat-value')?.textContent.trim();
        
        if (statLabel && statValue) {
            statsData[statLabel] = statValue;
        }
    });
    
    // Collect PER value if present
    const perValue = document.getElementById('perValue')?.textContent.trim();
    if (perValue) {
        statsData.perValue = perValue;
    }
    
    // Collect data from tables
    document.querySelectorAll('table').forEach((table, index) => {
        const tableId = table.id || `table_${index}`;
        statsData[tableId] = collectTableData(table);
    });
    
    // Collect data from charts
    document.querySelectorAll('.chart-container').forEach((chart, index) => {
        const chartId = chart.id || `chart_${index}`;
        statsData[`chart_${chartId}`] = { id: chartId };
    });
    
    return optimizeStatsData(statsData);
}

/**
 * Collect data from a table
 */
function collectTableData(table) {
    const tableData = {
        headers: [],
        rows: []
    };
    
    // Get headers
    const headerRow = table.querySelector('thead tr');
    if (headerRow) {
        headerRow.querySelectorAll('th').forEach(th => {
            tableData.headers.push(th.textContent.trim());
        });
    }
    
    // Get rows
    table.querySelectorAll('tbody tr').forEach(tr => {
        const rowData = [];
        tr.querySelectorAll('td').forEach(td => {
            rowData.push(td.textContent.trim());
        });
        tableData.rows.push(rowData);
    });
    
    return tableData;
}

/**
 * Optimize stats data for storage
 */
function optimizeStatsData(data) {
    // This is a placeholder for more sophisticated optimization
    // In a real implementation, you might:
    // 1. Remove redundant data
    // 2. Compress large datasets
    // 3. Convert string numbers to actual numbers
    // 4. Use more efficient data structures
    
    // For now, we'll just do some basic optimizations
    
    // Convert string numbers to actual numbers
    for (const key in data) {
        if (typeof data[key] === 'string' && !isNaN(data[key])) {
            // Check if it's an integer
            if (data[key].indexOf('.') === -1) {
                data[key] = parseInt(data[key]);
            } else {
                data[key] = parseFloat(data[key]);
            }
        }
    }
    
    return data;
}

/**
 * Collect filter parameters from the page
 */
function collectFilterParams() {
    const filterParams = {};
    
    // Look for filter form elements
    const filterForm = document.querySelector('form[method="get"]');
    if (filterForm) {
        const formData = new FormData(filterForm);
        for (const [key, value] of formData.entries()) {
            filterParams[key] = value;
        }
    }
    
    // Also check URL parameters
    const urlParams = new URLSearchParams(window.location.search);
    for (const [key, value] of urlParams.entries()) {
        if (key !== 'player_id' && key !== 'game_id') {  // Skip these as they're not filters
            filterParams[key] = value;
        }
    }
    
    return Object.keys(filterParams).length > 0 ? filterParams : null;
}

/**
 * Show a notification to the user
 */
function showNotification(message, type = 'success', duration = 5000) {
    // Create notification element if it doesn't exist
    let notificationContainer = document.getElementById('notification-container');
    if (!notificationContainer) {
        notificationContainer = document.createElement('div');
        notificationContainer.id = 'notification-container';
        notificationContainer.style.position = 'fixed';
        notificationContainer.style.top = '20px';
        notificationContainer.style.right = '20px';
        notificationContainer.style.zIndex = '9999';
        document.body.appendChild(notificationContainer);
    }
    
    // Create notification
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show`;
    notification.role = 'alert';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    // Add to container
    notificationContainer.appendChild(notification);
    
    // Auto-dismiss after duration
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => {
            notification.remove();
        }, 300);
    }, duration);
}

/**
 * Update the save button text
 */
function updateSaveButton(text) {
    const saveBtn = document.getElementById('saveStatsBtn');
    if (saveBtn) {
        saveBtn.innerHTML = `<i class="bi bi-save"></i> ${text}`;
    }
}

/**
 * Format a date string
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString();
}

/**
 * Get CSRF token from meta tag
 */
function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
}