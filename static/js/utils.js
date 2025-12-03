// static/js/utils.js - Utility Functions

// ============================================
// INPUT VALIDATION HELPERS
// ============================================

function hasHTMLLinks(content) {
    // Check for HTML links
    const htmlPattern = /<\s*a\s+[^>]*href\s*=/i;
    if (htmlPattern.test(content)) return true;

    // Check for markdown reference links: [1]: https://...
    const markdownRefPattern = /^\s*\[\d+\]\s*:\s*https?:\/\//m;
    if (markdownRefPattern.test(content)) return true;

    // Check for markdown inline links: [text](https://...)
    const markdownInlinePattern = /\[([^\]]+)\]\(https?:\/\/[^\)]+\)/;
    if (markdownInlinePattern.test(content)) return true;

    // Check for plain URLs (at least 2 to avoid false positives)
    const urlPattern = /https?:\/\/[^\s]+/g;
    const matches = content.match(urlPattern);
    if (matches && matches.length >= 2) return true;

    return false;
}

function countLinks(content) {
    let count = 0;

    const htmlPattern = /<\s*a\s+[^>]*href\s*=\s*["'][^"']+["'][^>]*>/gi;
    const htmlMatches = content.match(htmlPattern);
    if (htmlMatches) count += htmlMatches.length;

    const markdownRefPattern = /^\s*\[\d+\]\s*:\s*https?:\/\//gm;
    const refMatches = content.match(markdownRefPattern);
    if (refMatches) count += refMatches.length;

    const markdownInlinePattern = /\[([^\]]+)\]\(https?:\/\/[^\)]+\)/g;
    const inlineMatches = content.match(markdownInlinePattern);
    if (inlineMatches) count += inlineMatches.length;

    if (count === 0) {
        const urlPattern = /https?:\/\/[^\s]+/g;
        const urlMatches = content.match(urlPattern);
        if (urlMatches) count = urlMatches.length;
    }

    return count;
}

// ============================================
// TEXT HELPERS
// ============================================

function escapeHtml(unsafe) {
    if (!unsafe) return '';
    return unsafe
        .toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// ============================================
// EXPORT HELPERS
// ============================================

function exportResults() {
    const data = {
        llmVerification: AppState.currentLLMVerificationResults,
        factCheck: AppState.currentFactCheckResults,
        keyClaims: AppState.currentKeyClaimsResults,
        biasAnalysis: AppState.currentBiasResults,
        lieDetection: AppState.currentLieDetectionResults,
        timestamp: new Date().toISOString()
    };

    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `analysis-report-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}
