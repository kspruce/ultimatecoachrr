# -*- coding: utf-8 -*-
"""
Created on Tue May 20 15:15:32 2025

@author: kspruce
"""

def calculate_throw_distance(start_x, start_y, end_x, end_y):
    """Calculate throw distance in meters"""
    return ((end_x - start_x)**2 + (end_y - start_y)**2)**0.5

def is_break_throw(throw_position, field_position):
    """Determine if throw is a break throw based on field position"""
    # Implement break throw logic based on field position
    pass

def determine_possession(event_type):
    """Determine possession change based on event type"""
    possession_change_events = [
        'throwaway', 'drop', 'block', 'forced_turnover', 
        'unforced_turnover', 'callahan'
    ]
    return event_type in possession_change_events

def is_point_ending_event(event_type):
    """Check if event ends the point"""
    return event_type in ['goal', 'callahan', 'scored_on']