// static/js/utils.js - Utility Functions
// VeriFlow Redesign - Minimalist Theme

// ============================================
// TEXT UTILITIES
// ============================================

/**
 * Escape HTML entities to prevent XSS
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Truncate text to specified length
 */
function truncateText(text, maxLength = 200) {
    if (!text || text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

/**
 * Format number with commas
 */
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * Format duration in seconds to readable string
 */
function formatDuration(seconds) {
    if (seconds < 60) {
        return `${Math.round(seconds)}s`;
    } else if (seconds < 3600) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.round(seconds % 60);
        return `${mins}m ${secs}s`;
    } else {
        const hours = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        return `${hours}h ${mins}m`;
    }
}

// ============================================
// URL UTILITIES
// ============================================

/**
 * Validate URL format
 */
function isValidUrl(string) {
    try {
        const url = new URL(string);
        return url.protocol === 'http:' || url.protocol === 'https:';
    } catch (_) {
        return false;
    }
}

/**
 * Extract domain from URL
 */
function getDomainFromUrl(url) {
    try {
        return new URL(url).hostname;
    } catch (_) {
        return url;
    }
}

/**
 * Check if content contains HTML links
 */
function hasHTMLLinks(content) {
    if (!content) return false;
    
    // Check for various link patterns
    const patterns = [
        /<a\s+[^>]*href\s*=/i,                    // HTML anchor tags
        /\[(\d+)\]:\s*https?:\/\//,               // Markdown references [1]: https://...
        /\[[^\]]+\]\(https?:\/\/[^)]+\)/,         // Markdown inline [text](url)
        /https?:\/\/[^\s]+/g                       // Plain URLs
    ];
    
    // Check for HTML/Markdown patterns
    for (const pattern of patterns.slice(0, 3)) {
        if (pattern.test(content)) return true;
    }
    
    // Check for multiple plain URLs (at least 2)
    const urlMatches = content.match(patterns[3]);
    return urlMatches && urlMatches.length >= 2;
}

/**
 * Count links in content
 */
function countLinks(content) {
    if (!content) return 0;
    
    const urlPattern = /https?:\/\/[^\s<>"']+/g;
    const matches = content.match(urlPattern);
    return matches ? matches.length : 0;
}

// ============================================
// SCORE UTILITIES
// ============================================

/**
 * Get score class based on verification score
 */
function getScoreClass(score) {
    if (score <= 0.1) return 'debunked';
    if (score >= 0.9) return 'verified';
    if (score >= 0.7) return 'partial';
    return 'unverified';
}

/**
 * Get score label based on verification score
 */
function getScoreLabel(score) {
    if (score <= 0.1) return 'False';
    if (score >= 0.9) return 'Verified';
    if (score >= 0.7) return 'Partially Verified';
    return 'Unverified';
}

/**
 * Get color for score (using new palette)
 */
function getScoreColor(score) {
    if (score <= 0.1) return '#F06449';      // Tomato - error
    if (score >= 0.9) return '#6B9B6B';      // Green - success
    if (score >= 0.7) return '#E8B84A';      // Yellow - warning
    return '#9A9A9A';                         // Grey - neutral
}

// ============================================
// DATE UTILITIES
// ============================================

/**
 * Format date to readable string
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

/**
 * Get relative time string
 */
function getRelativeTime(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);
    
    if (diffSecs < 60) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return formatDate(dateString);
}

// ============================================
// EXPORT UTILITIES
// ============================================

/**
 * Download data as JSON file
 */
function downloadAsJson(data, filename) {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

/**
 * Copy text to clipboard
 */
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch (err) {
        console.error('Failed to copy:', err);
        return false;
    }
}

// ============================================
// DOM UTILITIES
// ============================================

/**
 * Create element with classes and attributes
 */
function createElement(tag, className = '', attributes = {}) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    Object.entries(attributes).forEach(([key, value]) => {
        el.setAttribute(key, value);
    });
    return el;
}

/**
 * Remove all children from element
 */
function clearElement(element) {
    while (element.firstChild) {
        element.removeChild(element.firstChild);
    }
}

/**
 * Debounce function calls
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
