/**
 * Stats Storage JavaScript - Fixed Version
 * Handles saving and retrieving stats to/from the database
 */

document.addEventListener('DOMContentLoaded', function() {
    // Check if we're on a stats page with a save button
    const saveStatsBtn = document.getElementById('saveStatsBtn');
    if (saveStatsBtn) {
        console.log("Save button found, adding click event listener");
        
        saveStatsBtn.addEventListener('click', function() {
            console.log("Save button clicked");
            
            // Determine which page we're on
            const currentPath = window.location.pathname;
            console.log("Current path:", currentPath);
            
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
    } else {
        console.log("Save button not found on the page");
    }
    
    // Check if we should load saved stats
    checkForSavedStats();
});

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
    // Show loading state
    const saveBtn = document.getElementById('saveStatsBtn');
    const originalText = saveBtn.innerHTML;
    saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...';
    saveBtn.disabled = true;
    
    // Collect all stats data from the page
    const statsData = collectIndexStatsData();
    console.log("Collected stats data:", statsData);
    
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
            version: 1
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
}

/**
 * Save team stats to database
 */
function saveTeamStats() {
    // Show loading state
    const saveBtn = document.getElementById('saveStatsBtn');
    const originalText = saveBtn.innerHTML;
    saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...';
    saveBtn.disabled = true;
    
    // Collect all stats data from the page
    const statsData = collectTeamStatsData();
    console.log("Collected team stats data:", statsData);
    
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
            version: 1
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
}

/**
 * Save game stats to database
 */
function saveGameStats(gameId) {
    // Show loading state
    const saveBtn = document.getElementById('saveStatsBtn');
    const originalText = saveBtn.innerHTML;
    saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...';
    saveBtn.disabled = true;
    
    // Collect all stats data from the page
    const statsData = collectGameStatsData();
    console.log("Collected game stats data:", statsData);
    
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
            version: 1
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
}

/**
 * Save player stats to database
 */
function savePlayerStats(playerId) {
    // Show loading state
    const saveBtn = document.getElementById('saveStatsBtn');
    const originalText = saveBtn.innerHTML;
    saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Saving...';
    saveBtn.disabled = true;
    
    // Collect all stats data from the page
    const statsData = collectPlayerStatsData();
    console.log("Collected player stats data:", statsData);
    
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
            version: 1
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
            showNotification(`Using saved stats from ${formatDate(data.updated_at)}`, 'info', 10000);
            
            // Update the save button to show "Update Stats"
            updateSaveButton('Update Stats');
            
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
            showNotification(`Using saved stats from ${formatDate(data.updated_at)}`, 'info', 10000);
            
            // Update the save button to show "Update Stats"
            updateSaveButton('Update Stats');
            
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
            showNotification(`Using saved stats from ${formatDate(data.updated_at)}`, 'info', 10000);
            
            // Update the save button to show "Update Stats"
            updateSaveButton('Update Stats');
            
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
            showNotification(`Using saved stats from ${formatDate(data.updated_at)}`, 'info', 10000);
            
            // Update the save button to show "Update Stats"
            updateSaveButton('Update Stats');
            
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
    console.log("Collecting index stats data");
    const statsData = {
        team_summary: {},
        players: [],
        recent_games: [],
        team_stats: [],
        player_stats: {},
        o_line_players: [],
        d_line_players: [],
        heatmap_data: '',
        connection_data: '',
        team_avg_stats: {}
    };
    
    try {
        // Collect stats from stat cards
        document.querySelectorAll('.stat-card').forEach(card => {
            const statLabel = card.querySelector('.stat-label')?.textContent.trim();
            const statValue = card.querySelector('.stat-value')?.textContent.trim();
            
            if (statLabel && statValue) {
                statsData.team_summary[statLabel] = statValue;
            }
        });
        
        // Collect team summary data
        const teamSummaryElement = document.getElementById('team-summary');
        if (teamSummaryElement) {
            // Try to get team summary data from a data attribute if available
            const teamSummaryData = teamSummaryElement.dataset.summary;
            if (teamSummaryData) {
                try {
                    statsData.team_summary = JSON.parse(teamSummaryData);
                } catch (e) {
                    console.error("Error parsing team summary data:", e);
                }
            }
        }
        
        // Collect player data
        document.querySelectorAll('.player-card, .player-row').forEach((playerElement, index) => {
            const playerName = playerElement.querySelector('.player-name')?.textContent.trim();
            const playerId = playerElement.dataset.playerId;
            
            if (playerName) {
                const playerData = {
                    id: playerId || index,
                    name: playerName
                };
                
                // Collect additional player data if available
                const jerseyNumber = playerElement.querySelector('.jersey-number')?.textContent.trim();
                if (jerseyNumber) {
                    playerData.jersey_number = jerseyNumber;
                }
                
                statsData.players.push(playerData);
            }
        });
        
        // Collect recent games data
        document.querySelectorAll('.game-card, .game-row').forEach((gameElement, index) => {
            const gameTitle = gameElement.querySelector('.game-title')?.textContent.trim();
            const gameId = gameElement.dataset.gameId;
            
            if (gameTitle) {
                const gameData = {
                    id: gameId || index,
                    title: gameTitle
                };
                
                // Collect additional game data if available
                const gameDate = gameElement.querySelector('.game-date')?.textContent.trim();
                if (gameDate) {
                    gameData.date = gameDate;
                }
                
                statsData.recent_games.push(gameData);
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
        
        // Try to get heatmap data if available
        const heatmapData = document.getElementById('heatmapData')?.textContent;
        if (heatmapData) {
            try {
                statsData.heatmap_data = JSON.parse(heatmapData);
            } catch (e) {
                console.error("Error parsing heatmap data:", e);
                statsData.heatmap_data = heatmapData;
            }
        }
        
        // Try to get connection data if available
        const connectionData = document.getElementById('connectionData')?.textContent;
        if (connectionData) {
            try {
                statsData.connection_data = JSON.parse(connectionData);
            } catch (e) {
                console.error("Error parsing connection data:", e);
                statsData.connection_data = connectionData;
            }
        }
        
        // Try to get all variables from the page context
        // This is a more comprehensive approach that should capture everything
        const pageVars = {};
        document.querySelectorAll('script').forEach(script => {
            const content = script.textContent;
            if (content) {
                // Look for variable assignments in the script
                const varMatches = content.match(/var\s+(\w+)\s*=\s*({[\s\S]*?});/g);
                if (varMatches) {
                    varMatches.forEach(match => {
                        const varName = match.match(/var\s+(\w+)/)[1];
                        try {
                            const varValue = JSON.parse(match.match(/=\s*({[\s\S]*?});/)[1]);
                            pageVars[varName] = varValue;
                        } catch (e) {
                            // Ignore parsing errors
                        }
                    });
                }
                
                // Look for JSON data in the script
                const jsonMatches = content.match(/JSON\.parse\('(.*?)'\)/g);
                if (jsonMatches) {
                    jsonMatches.forEach(match => {
                        try {
                            const jsonStr = match.match(/JSON\.parse\('(.*?)'\)/)[1];
                            const jsonData = JSON.parse(jsonStr);
                            if (typeof jsonData === 'object' && jsonData !== null) {
                                Object.assign(pageVars, jsonData);
                            }
                        } catch (e) {
                            // Ignore parsing errors
                        }
                    });
                }
            }
        });
        
        // Add page variables to stats data
        statsData.page_vars = pageVars;
        
        // Get all data attributes from the body element
        const bodyDataAttrs = {};
        const bodyElement = document.body;
        if (bodyElement.dataset) {
            Object.keys(bodyElement.dataset).forEach(key => {
                try {
                    bodyDataAttrs[key] = JSON.parse(bodyElement.dataset[key]);
                } catch (e) {
                    bodyDataAttrs[key] = bodyElement.dataset[key];
                }
            });
        }
        
        statsData.body_data = bodyDataAttrs;
        
        // Get all global variables that might contain stats
        const globalVars = ['team_summary', 'players', 'recent_games', 'team_stats', 'player_stats', 
                           'o_line_players', 'd_line_players', 'heatmap_data', 'connection_data', 
                           'team_avg_stats', 'performance_trends'];
        
        globalVars.forEach(varName => {
            if (window[varName] !== undefined) {
                statsData[varName] = window[varName];
            }
        });
        
        // Get the entire HTML of the main content area
        const mainContent = document.querySelector('main') || document.querySelector('.container-fluid');
        if (mainContent) {
            statsData.html_content = mainContent.innerHTML;
        }
        
    } catch (error) {
        console.error("Error collecting index stats data:", error);
    }
    
    return statsData;
}

/**
 * Collect team stats data from the page
 */
function collectTeamStatsData() {
    console.log("Collecting team stats data");
    const statsData = {
        team_summary: {},
        player_stats: {},
        performance_trends: {},
        o_line_players: [],
        d_line_players: [],
        o_line_efficiency: {},
        d_line_efficiency: {}
    };
    
    try {
        // Similar approach to collectIndexStatsData
        // Collect stats from stat cards
        document.querySelectorAll('.stat-card').forEach(card => {
            const statLabel = card.querySelector('.stat-label')?.textContent.trim();
            const statValue = card.querySelector('.stat-value')?.textContent.trim();
            
            if (statLabel && statValue) {
                statsData.team_summary[statLabel] = statValue;
            }
        });
        
        // Get the entire HTML of the main content area
        const mainContent = document.querySelector('main') || document.querySelector('.container-fluid');
        if (mainContent) {
            statsData.html_content = mainContent.innerHTML;
        }
        
        // Get all global variables that might contain stats
        const globalVars = ['team_summary', 'player_stats', 'performance_trends', 'o_line_players', 
                           'd_line_players', 'o_line_efficiency', 'd_line_efficiency'];
        
        globalVars.forEach(varName => {
            if (window[varName] !== undefined) {
                statsData[varName] = window[varName];
            }
        });
        
    } catch (error) {
        console.error("Error collecting team stats data:", error);
    }
    
    return statsData;
}

/**
 * Collect game stats data from the page
 */
function collectGameStatsData() {
    console.log("Collecting game stats data");
    const statsData = {
        game: {},
        team_stats: {},
        player_stats: [],
        heatmap_data: '',
        connections: ''
    };
    
    try {
        // Get game info
        const gameTitle = document.querySelector('h1')?.textContent.trim();
        if (gameTitle) {
            statsData.game.title = gameTitle;
        }
        
        // Collect stats from stat cards
        document.querySelectorAll('.stat-card').forEach(card => {
            const statLabel = card.querySelector('.stat-label')?.textContent.trim();
            const statValue = card.querySelector('.stat-value')?.textContent.trim();
            
            if (statLabel && statValue) {
                statsData.team_stats[statLabel] = statValue;
            }
        });
        
        // Get the entire HTML of the main content area
        const mainContent = document.querySelector('main') || document.querySelector('.container-fluid');
        if (mainContent) {
            statsData.html_content = mainContent.innerHTML;
        }
        
        // Get all global variables that might contain stats
        const globalVars = ['game', 'team_stats', 'player_stats', 'heatmap_data', 'connections'];
        
        globalVars.forEach(varName => {
            if (window[varName] !== undefined) {
                statsData[varName] = window[varName];
            }
        });
        
    } catch (error) {
        console.error("Error collecting game stats data:", error);
    }
    
    return statsData;
}

/**
 * Collect player stats data from the page
 */
function collectPlayerStatsData() {
    console.log("Collecting player stats data");
    const statsData = {
        player: {},
        stats: {},
        team_summary: {},
        player_games: [],
        throw_vectors: [],
        throw_stats: {}
    };
    
    try {
        // Get player info
        const playerName = document.querySelector('h1')?.textContent.trim();
        if (playerName) {
            statsData.player.name = playerName;
        }
        
        // Collect stats from stat cards
        document.querySelectorAll('.stat-card').forEach(card => {
            const statLabel = card.querySelector('.stat-label')?.textContent.trim();
            const statValue = card.querySelector('.stat-value')?.textContent.trim();
            
            if (statLabel && statValue) {
                statsData.stats[statLabel] = statValue;
            }
        });
        
        // Collect PER value if present
        const perValue = document.getElementById('perValue')?.textContent.trim();
        if (perValue) {
            statsData.stats.perValue = perValue;
        }
        
        // Get the entire HTML of the main content area
        const mainContent = document.querySelector('main') || document.querySelector('.container-fluid');
        if (mainContent) {
            statsData.html_content = mainContent.innerHTML;
        }
        
        // Get all global variables that might contain stats
        const globalVars = ['player', 'stats', 'team_summary', 'player_games', 'throw_vectors', 'throw_stats'];
        
        globalVars.forEach(varName => {
            if (window[varName] !== undefined) {
                statsData[varName] = window[varName];
            }
        });
        
    } catch (error) {
        console.error("Error collecting player stats data:", error);
    }
    
    return statsData;
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

// Add a global function to recalculate stats
document.addEventListener('DOMContentLoaded', function() {
    const recalculateBtn = document.getElementById('recalculateStatsBtn');
    if (recalculateBtn) {
        recalculateBtn.addEventListener('click', function(e) {
            e.preventDefault();
            // Add a parameter to force recalculation
            const url = new URL(window.location.href);
            url.searchParams.set('recalculate', 'true');
            window.location.href = url.toString();
        });
    }
});