document.addEventListener('DOMContentLoaded', function() {
  // Variables to track state
  let currentPossession = 'offense'; // or 'defense'
  let selectedPlayers = [];
  let pointEvents = [];
  let lastThrower = null;
  
  // Update player counts when checkboxes are clicked
  document.querySelectorAll('.player-checkbox').forEach(checkbox => {
    checkbox.addEventListener('change', updatePlayerCounts);
  });
  
  // Gender ratio change handler
  document.querySelectorAll('input[name="gender_ratio"]').forEach(radio => {
    radio.addEventListener('change', function() {
      const ratio = this.value;
      const [mmpRequired, fmpRequired] = ratio.split('-').map(Number);
      
      document.getElementById('mmp-required').textContent = mmpRequired;
      document.getElementById('fmp-required').textContent = fmpRequired;
      
      updatePlayerCounts();
    });
  });
  
  // Line type change handler
  document.querySelectorAll('input[name="line_type"]').forEach(radio => {
    radio.addEventListener('change', function() {
      const lineType = this.value;
      document.getElementById('current-line-type').textContent = lineType;
      
      // Show/hide pull section based on line type
      if (lineType === 'D-line') {
        document.getElementById('pull-section').style.display = 'block';
        currentPossession = 'defense';
        updateEventButtons();
      } else {
        document.getElementById('pull-section').style.display = 'none';
        currentPossession = 'offense';
        updateEventButtons();
      }
    });
  });
  
  // Power line button handler
  document.getElementById('power-line').addEventListener('click', function() {
    // Get the gender ratio
    const ratio = document.querySelector('input[name="gender_ratio"]:checked').value;
    const [mmpRequired, fmpRequired] = ratio.split('-').map(Number);
    
    // Uncheck all current selections
    document.querySelectorAll('.player-checkbox:checked').forEach(checkbox => {
      checkbox.checked = false;
    });
    
    // Get top players by +/- for each gender
    const mmpPlayers = Array.from(document.querySelectorAll('.mmp-checkbox'))
      .map(checkbox => {
        const plusMinus = parseInt(checkbox.closest('.player-card').querySelector('.plus-minus').textContent) || 0;
        return { id: checkbox.value, plusMinus: plusMinus, element: checkbox };
      })
      .sort((a, b) => b.plusMinus - a.plusMinus)
      .slice(0, mmpRequired);
    
    const fmpPlayers = Array.from(document.querySelectorAll('.fmp-checkbox'))
      .map(checkbox => {
        const plusMinus = parseInt(checkbox.closest('.player-card').querySelector('.plus-minus').textContent) || 0;
        return { id: checkbox.value, plusMinus: plusMinus, element: checkbox };
      })
      .sort((a, b) => b.plusMinus - a.plusMinus)
      .slice(0, fmpRequired);
    
    // Check the top players
    mmpPlayers.forEach(player => player.element.checked = true);
    fmpPlayers.forEach(player => player.element.checked = true);
    
    // Update counts
    updatePlayerCounts();
  });
  
  // Start point button handler
  document.getElementById('start-point').addEventListener('click', function() {
    // Collect selected players
    selectedPlayers = Array.from(document.querySelectorAll('.player-checkbox:checked'))
      .map(checkbox => {
        const label = checkbox.nextElementSibling;
        return {
          id: checkbox.value,
          name: label.textContent.trim(),
          jersey: label.querySelector('.badge').textContent,
          gender: checkbox.dataset.gender
        };
      });
    
    // Populate player chips
    const activePlayersContainer = document.getElementById('active-players');
    activePlayersContainer.innerHTML = '';
    
    selectedPlayers.forEach(player => {
      const chip = document.createElement('span');
      chip.className = 'badge bg-primary me-1 mb-1 player-chip';
      chip.textContent = `#${player.jersey} ${player.name}`;
      chip.dataset.playerId = player.id;
      activePlayersContainer.appendChild(chip);
    });
    
    // Populate player dropdown
    const playerSelect = document.getElementById('event-player');
    playerSelect.innerHTML = '<option value="">Select Player</option>';
    
    selectedPlayers.forEach(player => {
      const option = document.createElement('option');
      option.value = player.id;
      option.textContent = `#${player.jersey} ${player.name}`;
      playerSelect.appendChild(option);
    });
    
    // Populate puller dropdown if D-line
    if (document.querySelector('input[name="line_type"]:checked').value === 'D-line') {
      const pullerSelect = document.getElementById('puller');
      pullerSelect.innerHTML = '<option value="">Select Puller</option>';
      
      selectedPlayers.forEach(player => {
        const option = document.createElement('option');
        option.value = player.id;
        option.textContent = `#${player.jersey} ${player.name}`;
        pullerSelect.appendChild(option);
      });
      
      document.getElementById('pull-section').style.display = 'block';
      currentPossession = 'defense';
    } else {
      document.getElementById('pull-section').style.display = 'none';
      currentPossession = 'offense';
    }
    
    // Show point tracking interface
    document.getElementById('point-tracking').style.display = 'block';
    
    // Update event buttons based on possession
    updateEventButtons();
    
    // Clear event log
    document.getElementById('event-log').innerHTML = '';
    pointEvents = [];
  });
  
  // Event button handlers
  document.querySelectorAll('.event-btn').forEach(button => {
    button.addEventListener('click', function() {
      const eventType = this.dataset.event;
      const playerId = document.getElementById('event-player').value;
      
      if (!playerId) {
        alert('Please select a player first');
        return;
      }
      
      const player = selectedPlayers.find(p => p.id === playerId);
      
      // Record the event
      const event = {
        type: eventType,
        player_id: playerId,
        player_name: player ? `#${player.jersey} ${player.name}` : 'Unknown Player',
        timestamp: new Date().toISOString()
      };
      
      // Special handling for certain events
      if (eventType === 'score') {
        // If someone scores, they must have caught it from someone
        if (lastThrower) {
          // Record an assist for the last thrower
          const assistEvent = {
            type: 'assist',
            player_id: lastThrower.id,
            player_name: lastThrower.name,
            timestamp: new Date().toISOString()
          };
          pointEvents.push(assistEvent);
          addEventToLog(assistEvent);
        }
        
        // We scored, so end the point
        setTimeout(() => {
          document.getElementById('we-scored').click();
        }, 500);
      }
      
      if (eventType === 'callahan') {
        // We scored, so end the point
        setTimeout(() => {
          document.getElementById('we-scored').click();
        }, 500);
      }
      
      if (eventType === 'throwaway' || eventType === 'stall' || eventType === 'drop') {
        // Turnover, switch possession
        currentPossession = currentPossession === 'offense' ? 'defense' : 'offense';
        updateEventButtons();
      }
      
      if (eventType === 'block' || eventType === 'pickup') {
        // Block or pickup, switch possession
        currentPossession = currentPossession === 'offense' ? 'defense' : 'offense';
        updateEventButtons();
      }
      
      // For throws, track the last thrower
      if (eventType === 'catch') {
        lastThrower = {
          id: playerId,
          name: player ? `#${player.jersey} ${player.name}` : 'Unknown Player'
        };
      }
      
      // Add event to array and log
      pointEvents.push(event);
      addEventToLog(event);
      
      // Reset player selection
      document.getElementById('event-player').value = '';
    });
  });
  
  // Toggle possession button
  document.getElementById('toggle-possession').addEventListener('click', function() {
    currentPossession = currentPossession === 'offense' ? 'defense' : 'offense';
    updateEventButtons();
    
    // Add event to log
    const event = {
      type: 'possession_change',
      description: `Switched to ${currentPossession}`,
      timestamp: new Date().toISOString()
    };
    pointEvents.push(event);
    addEventToLog(event);
  });
  
  // End point handlers
  document.getElementById('we-scored').addEventListener('click', function() {
    endPoint('scored');
  });
  
  document.getElementById('they-scored').addEventListener('click', function() {
    endPoint('conceded');
  });
  
  // Pull handlers
  document.getElementById('pull-in').addEventListener('click', function() {
    const pullerId = document.getElementById('puller').value;
    if (!pullerId) {
      alert('Please select a puller');
      return;
    }
    
    const puller = selectedPlayers.find(p => p.id === pullerId);
    
    // Record pull event
    const event = {
      type: 'pull',
      result: 'in',
      player_id: pullerId,
      player_name: puller ? `#${puller.jersey} ${puller.name}` : 'Unknown Player',
      timestamp: new Date().toISOString()
    };
    
    pointEvents.push(event);
    addEventToLog(event);
    
    // Hide pull section after recording
    document.getElementById('pull-section').style.display = 'none';
  });
  
  document.getElementById('pull-out').addEventListener('click', function() {
    const pullerId = document.getElementById('puller').value;
    if (!pullerId) {
      alert('Please select a puller');
      return;
    }
    
    const puller = selectedPlayers.find(p => p.id === pullerId);
    
    // Record pull event
    const event = {
      type: 'pull',
      result: 'out',
      player_id: pullerId,
      player_name: puller ? `#${puller.jersey} ${puller.name}` : 'Unknown Player',
      timestamp: new Date().toISOString()
    };
    
    pointEvents.push(event);
    addEventToLog(event);
    
    // Hide pull section after recording
    document.getElementById('pull-section').style.display = 'none';
  });
  
  // Helper functions
  function updatePlayerCounts() {
    const mmpChecked = document.querySelectorAll('.mmp-checkbox:checked').length;
    const fmpChecked = document.querySelectorAll('.fmp-checkbox:checked').length;
    const totalChecked = mmpChecked + fmpChecked;
    
    document.getElementById('mmp-count').textContent = mmpChecked;
    document.getElementById('fmp-count').textContent = fmpChecked;
    
    const mmpRequired = parseInt(document.getElementById('mmp-required').textContent);
    const fmpRequired = parseInt(document.getElementById('fmp-required').textContent);
    
    const lineStatus = document.getElementById('line-status');
    const startButton = document.getElementById('start-point');
    
    if (totalChecked === 7 && mmpChecked === mmpRequired && fmpChecked === fmpRequired) {
      lineStatus.className = 'alert alert-success';
      lineStatus.textContent = 'Line complete! Ready to start point.';
      startButton.disabled = false;
    } else if (totalChecked > 7) {
      lineStatus.className = 'alert alert-danger';
      lineStatus.textContent = `Too many players selected (${totalChecked}/7)`;
      startButton.disabled = true;
    } else if (mmpChecked > mmpRequired) {
      lineStatus.className = 'alert alert-warning';
      lineStatus.textContent = `Too many MMP players (${mmpChecked}/${mmpRequired})`;
      startButton.disabled = true;
    } else if (fmpChecked > fmpRequired) {
      lineStatus.className = 'alert alert-warning';
      lineStatus.textContent = `Too many FMP players (${fmpChecked}/${fmpRequired})`;
      startButton.disabled = true;
    } else {
      lineStatus.className = 'alert alert-info';
      lineStatus.textContent = `Select ${7 - totalChecked} more players (${mmpRequired - mmpChecked} MMP, ${fmpRequired - fmpChecked} FMP)`;
      startButton.disabled = true;
    }
  }
  
  function updateEventButtons() {
    if (currentPossession === 'offense') {
      document.getElementById('offense-events').style.display = 'block';
      document.getElementById('defense-events').style.display = 'none';
    } else {
      document.getElementById('offense-events').style.display = 'none';
      document.getElementById('defense-events').style.display = 'block';
    }
  }
  
  function addEventToLog(event) {
    const logContainer = document.getElementById('event-log');
    const eventElement = document.createElement('div');
    eventElement.className = 'event-item';
    
    let eventText = '';
    
    switch (event.type) {
      case 'catch':
        eventText = `${event.player_name} caught the disc`;
        eventElement.className += ' text-primary';
        break;
      case 'drop':
        eventText = `${event.player_name} dropped the disc`;
        eventElement.className += ' text-danger';
        break;
      case 'score':
        eventText = `${event.player_name} scored!`;
        eventElement.className += ' text-success fw-bold';
        break;
      case 'throwaway':
        eventText = `${event.player_name} threw the disc away`;
        eventElement.className += ' text-danger';
        break;
      case 'stall':
        eventText = `${event.player_name} got stalled`;
        eventElement.className += ' text-danger';
        break;
      case 'block':
        eventText = `${event.player_name} got a block!`;
        eventElement.className += ' text-success';
        break;
      case 'pickup':
        eventText = `${event.player_name} picked up the disc`;
        eventElement.className += ' text-primary';
        break;
      case 'callahan':
        eventText = `${event.player_name} scored a Callahan!`;
        eventElement.className += ' text-success fw-bold';
        break;
      case 'assist':
        eventText = `${event.player_name} threw an assist`;
        eventElement.className += ' text-success';
        break;
      case 'pull':
        eventText = `${event.player_name} pulled (${event.result})`;
        eventElement.className += ' text-secondary';
        break;
      case 'possession_change':
        eventText = event.description;
        eventElement.className += ' text-info fst-italic';
        break;
      default:
        eventText = `${event.type}: ${event.player_name}`;
    }
    
    eventElement.textContent = eventText;
    logContainer.appendChild(eventElement);
    
    // Scroll to bottom
    logContainer.scrollTop = logContainer.scrollHeight;
  }
  

    
    // Send all events to server
    fetch('/api/record-point', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
      },
      body: JSON.stringify({
        point_number: document.getElementById('next_point_number').value,
        line_type: document.querySelector('input[name="line_type"]:checked').value,
        gender_ratio: document.querySelector('input[name="gender_ratio"]:checked').value,
        players: selectedPlayers.map(p => p.id),
        events: pointEvents,
        outcome: outcome
      })
    })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        // Reset UI for next point
        document.getElementById('point-tracking').style.display = 'none';
        
        // Uncheck all players
        document.querySelectorAll('.player-checkbox:checked').forEach(checkbox => {
          checkbox.checked = false;
        });
        
        // Update player counts
        updatePlayerCounts();
        
        // Update game score
        document.getElementById('our_score').textContent = data.our_score;
        document.getElementById('their_score').textContent = data.their_score;
        
        // Update next point number
        document.getElementById('next_point_number').value = data.next_point_number;
        
        // Show success message
        alert(`Point recorded! Score: ${data.our_score}-${data.their_score}`);
      } else {
        alert('Error recording point: ' + data.error);
      }
    })
    .catch(error => {
      console.error('Error:', error);
      alert('Error recording point. See console for details.');
    });
  }
});

function endPoint(outcome) {
  // Add final outcome to events
  const event = {
    type: 'point_outcome',
    outcome: outcome,
    timestamp: new Date().toISOString()
  };
  pointEvents.push(event);
  
  // Create point data object
  const pointData = {
    game_id: document.getElementById('game-id').value,
    point_number: document.getElementById('current-point-number').textContent,
    line_type: document.querySelector('input[name="line_type"]:checked').value,
    gender_ratio: document.querySelector('input[name="gender_ratio"]:checked').value,
    players: selectedPlayers.map(p => p.id),
    events: pointEvents,
    outcome: outcome
  };
  
  // Send all events to server
  fetch('/gameday/api/record-point', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
    },
    body: JSON.stringify(pointData)
  })
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      // Reset UI for next point
      document.getElementById('point-tracking').style.display = 'none';
      document.getElementById('line-selection').style.display = 'block';
      
      // Uncheck all players
      document.querySelectorAll('.player-checkbox:checked').forEach(checkbox => {
        checkbox.checked = false;
      });
      
      // Update player counts
      updatePlayerCounts();
      
      // Update game score
      document.getElementById('our-score').textContent = data.our_score;
      document.getElementById('their-score').textContent = data.their_score;
      document.getElementById('current-score').textContent = `${data.our_score}-${data.their_score}`;
      
      // Update next point number
      document.getElementById('next-point-number').textContent = data.next_point_number;
      document.getElementById('next-point-number-input').value = data.next_point_number;
      
      // Show success message
      const toast = document.createElement('div');
      toast.className = 'position-fixed top-0 end-0 p-3';
      toast.style.zIndex = '1070';
      toast.innerHTML = `
        <div class="toast show ${outcome === 'scored' ? 'bg-success' : 'bg-danger'} text-white" role="alert">
          <div class="toast-header ${outcome === 'scored' ? 'bg-success' : 'bg-danger'} text-white">
            <strong class="me-auto">Point ${outcome === 'scored' ? 'Scored' : 'Conceded'}</strong>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
          </div>
          <div class="toast-body">
            Score: ${data.our_score}-${data.their_score}
          </div>
        </div>
      `;
      document.body.appendChild(toast);
      
      // Remove toast after 3 seconds
      setTimeout(() => {
        toast.remove();
      }, 3000);
      
      // Reload the game summary section to update stats
      location.reload();
    } else {
      alert('Error recording point: ' + data.error);
    }
  })
  .catch(error => {
    console.error('Error recording point:', error);
    alert('Error recording point. Please try again.');
  });
}



