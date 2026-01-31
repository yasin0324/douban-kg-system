#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Data validation and cleaning module

Provides utility functions for data validation and transformation
"""

import re
from datetime import datetime


def match_year(text):
    """Extract 4-digit year from text"""
    if not text:
        return None
    match = re.search(r'(\d{4})', text)
    if match:
        year = int(match.group(1))
        if 1900 <= year <= 2100:
            return year
    return None


def match_date(text):
    """Extract date from text in various formats"""
    if not text:
        return None
    
    # Try to match YYYY-MM-DD format
    match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', text)
    if match:
        return f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
    
    # Try to match YYYY-MM format
    match = re.search(r'(\d{4})-(\d{1,2})', text)
    if match:
        return f"{match.group(1)}-{match.group(2).zfill(2)}-01"
    
    # Try to match YYYY format
    match = re.search(r'(\d{4})', text)
    if match:
        return f"{match.group(1)}-01-01"
    
    return None


def str_to_date(date_str):
    """Convert string to date object"""
    if not date_str:
        return None
    
    try:
        # Try YYYY-MM-DD format
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        pass
    
    try:
        # Try YYYY-MM format
        return datetime.strptime(date_str, '%Y-%m').date()
    except (ValueError, TypeError):
        pass
    
    try:
        # Try YYYY format
        return datetime.strptime(date_str, '%Y').date()
    except (ValueError, TypeError):
        pass
    
    return None


def process_slash_str(text):
    """Process slash-separated strings, remove extra spaces"""
    if not text:
        return ''
    
    # Replace multiple slashes with single slash
    text = re.sub(r'/+', '/', text)
    # Remove leading/trailing slashes
    text = text.strip('/')
    # Remove extra spaces
    text = ' '.join(text.split())
    
    return text


def process_url(url):
    """Process and validate URL"""
    if not url:
        return ''
    
    url = url.strip()
    
    # Ensure URL starts with http:// or https://
    if url and not url.startswith(('http://', 'https://')):
        url = 'http://' + url
    
    return url
