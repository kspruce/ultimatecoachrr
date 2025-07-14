window.sessionManager = {
    deleteSession: function(sessionId) {
        console.log('Delete session called for ID:', sessionId);
        
        if (confirm('Are you sure you want to delete this session? This cannot be undone.')) {
            const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
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
                    alert('Error: ' + (data.message || 'Failed to delete session'));
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Failed to delete session. Please try again.');
            });
        }
    }
};

// Verify script loading
console.log('Session management script loaded');
