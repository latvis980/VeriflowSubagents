// Fact Checker App - JavaScript

// DOM Elements
const htmlInput = document.getElementById('htmlInput');
const checkBtn = document.getElementById('checkBtn');
const clearBtn = document.getElementById('clearBtn');
const statusSection = document.getElementById('statusSection');
const resultsSection = document.getElementById('resultsSection');
const errorSection = document.getElementById('errorSection');
const factsList = document.getElementById('factsList');
const exportBtn = document.getElementById('exportBtn');
const newCheckBtn = document.getElementById('newCheckBtn');
const retryBtn = document.getElementById('retryBtn');

// State
let currentResults = null;

// Event Listeners
checkBtn.addEventListener('click', handleCheckFacts);
clearBtn.addEventListener('click', handleClear);
exportBtn.addEventListener('click', handleExport);
newCheckBtn.addEventListener('click', handleNewCheck);
retryBtn.addEventListener('click', handleRetry);

// Allow Ctrl/Cmd + Enter to submit
htmlInput.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        handleCheckFacts();
    }
});

/**
 * Main function to check facts
 */
async function handleCheckFacts() {
    const htmlContent = htmlInput.value.trim();

    // Validation
    if (!htmlContent) {
        showError('Please paste some HTML content to check.');
        return;
    }

    // Show loading state
    setLoadingState(true);
    hideAllSections();
    showSection(statusSection);
    updateStatus('Processing...', 'Analyzing your content and checking sources');

    try {
        // Call API
        const response = await fetch('/api/check', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                html_content: htmlContent
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.message || `Server error: ${response.status}`);
        }

        const results = await response.json();
        currentResults = results;

        // Show results
        displayResults(results);

    } catch (error) {
        console.error('Error checking facts:', error);
        showError(error.message || 'An unexpected error occurred. Please try again.');
    } finally {
        setLoadingState(false);
    }
}

/**
 * Display results in the UI
 */
function displayResults(results) {
    hideAllSections();
    showSection(resultsSection);

    // Update summary
    document.getElementById('totalFacts').textContent = results.summary.total_facts;
    document.getElementById('accurateFacts').textContent = results.summary.accurate;
    document.getElementById('goodFacts').textContent = results.summary.good_match;
    document.getElementById('questionableFacts').textContent = results.summary.questionable;
    document.getElementById('avgScore').textContent = results.summary.avg_score.toFixed(2);
    document.getElementById('sessionId').textContent = results.session_id;
    document.getElementById('duration').textContent = `${results.duration.toFixed(1)}s`;

    // Update LangSmith link
    if (results.langsmith_url) {
        document.getElementById('langsmithUrl').href = results.langsmith_url;
    }

    // Display facts
    displayFacts(results.facts);

    // Scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/**
 * Display individual facts
 */
function displayFacts(facts) {
    factsList.innerHTML = '';

    if (!facts || facts.length === 0) {
        factsList.innerHTML = '<p style="text-align: center; color: var(--text-secondary);">No facts found.</p>';
        return;
    }

    facts.forEach(fact => {
        const factCard = createFactCard(fact);
        factsList.appendChild(factCard);
    });
}

/**
 * Create a fact card element
 */
function createFactCard(fact) {
    const card = document.createElement('div');
    card.className = `fact-card ${getScoreClass(fact.match_score)}`;

    const scoreEmoji = getScoreEmoji(fact.match_score);
    const scoreColor = getScoreColor(fact.match_score);

    card.innerHTML = `
        <div class="fact-header">
            <span class="fact-id">${fact.fact_id}</span>
            <div class="fact-score">
                <span class="score-badge ${getScoreClass(fact.match_score)}">
                    ${scoreEmoji} ${fact.match_score.toFixed(2)}
                </span>
            </div>
        </div>

        <div class="fact-statement">
            ${escapeHtml(fact.statement)}
        </div>

        <div class="fact-assessment">
            <div class="fact-assessment-label">Assessment</div>
            ${escapeHtml(fact.assessment)}
        </div>

        ${fact.discrepancies && fact.discrepancies !== 'none' ? `
            <div class="fact-discrepancies">
                <div class="fact-discrepancies-label">⚠️ Discrepancies</div>
                ${escapeHtml(fact.discrepancies)}
            </div>
        ` : ''}

        ${fact.reasoning ? `
            <details style="margin-top: 1rem;">
                <summary style="cursor: pointer; font-weight: 600; color: var(--text-secondary);">
                    View Reasoning
                </summary>
                <div style="margin-top: 0.5rem; padding: 1rem; background: white; border-radius: 6px; border: 1px solid var(--border-color);">
                    ${escapeHtml(fact.reasoning)}
                </div>
            </details>
        ` : ''}
    `;

    return card;
}

/**
 * Get score class for styling
 */
function getScoreClass(score) {
    if (score >= 0.9) return 'accurate';
    if (score >= 0.7) return 'good';
    return 'questionable';
}

/**
 * Get emoji for score
 */
function getScoreEmoji(score) {
    if (score >= 0.9) return '✅';
    if (score >= 0.7) return '⚠️';
    return '❌';
}

/**
 * Get color for score
 */
function getScoreColor(score) {
    if (score >= 0.9) return 'var(--success-color)';
    if (score >= 0.7) return 'var(--warning-color)';
    return 'var(--danger-color)';
}

/**
 * Handle clear button
 */
function handleClear() {
    htmlInput.value = '';
    htmlInput.focus();
}

/**
 * Handle new check button
 */
function handleNewCheck() {
    hideAllSections();
    htmlInput.value = '';
    htmlInput.focus();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

/**
 * Handle retry button
 */
function handleRetry() {
    hideAllSections();
    htmlInput.focus();
}

/**
 * Handle export button
 */
function handleExport() {
    if (!currentResults) return;

    const dataStr = JSON.stringify(currentResults, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);

    const link = document.createElement('a');
    link.href = url;
    link.download = `fact-check-report-${currentResults.session_id}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

/**
 * Show error message
 */
function showError(message) {
    hideAllSections();
    showSection(errorSection);
    document.getElementById('errorMessage').textContent = message;
}

/**
 * Update status message
 */
function updateStatus(title, message) {
    document.getElementById('statusTitle').textContent = title;
    document.getElementById('statusMessage').textContent = message;
}

/**
 * Set loading state for button
 */
function setLoadingState(isLoading) {
    checkBtn.disabled = isLoading;

    const btnText = checkBtn.querySelector('.btn-text');
    const btnLoading = checkBtn.querySelector('.btn-loading');

    if (isLoading) {
        btnText.style.display = 'none';
        btnLoading.style.display = 'flex';
    } else {
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
    }
}

/**
 * Hide all sections
 */
function hideAllSections() {
    statusSection.style.display = 'none';
    resultsSection.style.display = 'none';
    errorSection.style.display = 'none';
}

/**
 * Show a section
 */
function showSection(section) {
    section.style.display = 'block';
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Initialize app
 */
function init() {
    console.log('Fact Checker initialized');
    htmlInput.focus();

    // Check health endpoint
    checkHealth();
}

/**
 * Check API health
 */
async function checkHealth() {
    try {
        const response = await fetch('/api/health');
        const data = await response.json();
        console.log('Health check:', data);
    } catch (error) {
        console.warn('Health check failed:', error);
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}