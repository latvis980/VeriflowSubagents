// static/app.js - Real-time progress streaming version

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
let activeEventSource = null;

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

    if (!htmlContent) {
        showError('Please paste some content to check.');
        return;
    }

    // Close any existing stream
    if (activeEventSource) {
        activeEventSource.close();
        activeEventSource = null;
    }

    setLoadingState(true);
    hideAllSections();
    showSection(statusSection);
    updateStatus('Starting...', 'Initializing fact-check process...');

    try {
        // Start the job
        const startResponse = await fetch('/api/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ html_content: htmlContent })
        });

        if (!startResponse.ok) {
            const errorData = await startResponse.json();
            throw new Error(errorData.message || `Server error: ${startResponse.status}`);
        }

        const { job_id } = await startResponse.json();
        console.log('Job started:', job_id);

        // Stream progress and wait for completion
        const result = await streamJobProgress(job_id);

        currentResults = result;
        displayResults(result);

    } catch (error) {
        console.error('Error checking facts:', error);
        showError(error.message || 'An unexpected error occurred. Please try again.');
    } finally {
        setLoadingState(false);
        if (activeEventSource) {
            activeEventSource.close();
            activeEventSource = null;
        }
    }
}

/**
 * Stream real-time progress using Server-Sent Events
 */
function streamJobProgress(jobId) {
    return new Promise((resolve, reject) => {
        const eventSource = new EventSource(`/api/job/${jobId}/stream`);
        activeEventSource = eventSource;
        let progressLog = [];

        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                // Check if done
                if (data.done) {
                    eventSource.close();
                    activeEventSource = null;

                    // Fetch final result
                    fetch(`/api/job/${jobId}`)
                        .then(res => res.json())
                        .then(jobData => {
                            if (jobData.status === 'completed') {
                                resolve(jobData.result);
                            } else {
                                reject(new Error(jobData.error || 'Job failed'));
                            }
                        })
                        .catch(err => reject(err));
                    return;
                }

                // Display progress
                if (data.message) {
                    progressLog.push(data.message);
                    updateProgressDisplay(data.message, progressLog);
                }
            } catch (err) {
                console.error('Error parsing progress:', err);
            }
        };

        eventSource.onerror = (error) => {
            console.error('EventSource error:', error);
            eventSource.close();
            activeEventSource = null;
            reject(new Error('Connection lost. Please try again.'));
        };

        // Timeout after 10 minutes
        setTimeout(() => {
            if (activeEventSource === eventSource) {
                eventSource.close();
                activeEventSource = null;
                reject(new Error('Request timeout after 10 minutes'));
            }
        }, 600000);
    });
}

/**
 * Update progress display with scrolling log
 */
function updateProgressDisplay(latestMessage, fullLog) {
    const statusTitle = document.getElementById('statusTitle');
    const statusMessage = document.getElementById('statusMessage');

    statusTitle.textContent = 'Processing...';

    // Show latest message prominently
    const recentMessages = fullLog.slice(-10).reverse();

    statusMessage.innerHTML = `
        <div style="font-weight: 600; font-size: 1.1em; margin-bottom: 1rem; color: var(--text-primary);">
            ${escapeHtml(latestMessage)}
        </div>
        <div style="max-height: 250px; overflow-y: auto; font-size: 0.9em; opacity: 0.85; border-top: 1px solid var(--border-color); padding-top: 1rem;">
            <div style="font-weight: 600; margin-bottom: 0.5rem; font-size: 0.85em; text-transform: uppercase; color: var(--text-secondary);">Recent Activity</div>
            ${recentMessages.map(msg => `<div style="padding: 0.25rem 0;">• ${escapeHtml(msg)}</div>`).join('')}
        </div>
    `;
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

    // Show pipeline info
    const summaryCard = document.querySelector('.summary-card');
    const existingPipelineInfo = summaryCard.querySelector('.pipeline-info');
    if (existingPipelineInfo) {
        existingPipelineInfo.remove();
    }

    const pipelineInfo = document.createElement('div');
    pipelineInfo.className = 'pipeline-info';
    pipelineInfo.style.cssText = 'margin-top: 1rem; padding: 0.75rem; background: rgba(255,255,255,0.15); border-radius: 6px; font-size: 0.9rem;';

    const pipelineName = results.methodology === 'web_search_verification' 
        ? '🔍 Web Search Pipeline' 
        : '🔗 LLM Output Pipeline';

    pipelineInfo.innerHTML = `
        <strong>Pipeline Used:</strong> ${pipelineName}
        ${results.statistics ? `
            <div style="margin-top: 0.5rem; font-size: 0.85rem; opacity: 0.9;">
                ${results.statistics.total_searches ? `Searches: ${results.statistics.total_searches} • ` : ''}
                ${results.statistics.total_sources_found ? `Sources Found: ${results.statistics.total_sources_found} • ` : ''}
                ${results.statistics.credible_sources_identified ? `Credible: ${results.statistics.credible_sources_identified} • ` : ''}
                Sources Scraped: ${results.statistics.sources_scraped || results.total_sources_scraped || 0}
            </div>
        ` : ''}
    `;

    summaryCard.appendChild(pipelineInfo);

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

    // Add sorting header
    const sortingHeader = document.createElement('div');
    sortingHeader.className = 'sorting-header';
    sortingHeader.innerHTML = `
        <div style="background: #f8f9fa; padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem; border-left: 4px solid #6c757d;">
            <div style="font-weight: 600; margin-bottom: 0.5rem; color: #495057;">
                📊 Facts ordered by accuracy score (most questionable first)
            </div>
            <div style="font-size: 0.9rem; color: #6c757d;">
                Review the lowest-scoring facts first to identify potential issues
            </div>
        </div>
    `;
    factsList.appendChild(sortingHeader);

    // Display facts
    facts.forEach((fact, index) => {
        const factCard = createFactCard(fact, index);
        factsList.appendChild(factCard);
    });
}

/**
 * Create a fact card element
 */
function createFactCard(fact, index) {
    const card = document.createElement('div');
    card.className = `fact-card ${getScoreClass(fact.match_score)}`;
    card.setAttribute('data-score', fact.match_score.toFixed(2));

    const scoreEmoji = getScoreEmoji(fact.match_score);
    const priorityIndicator = getPriorityIndicator(fact.match_score, index);

    card.innerHTML = `
        <div class="fact-header">
            <span class="fact-id">${priorityIndicator}${fact.fact_id}</span>
            <div class="fact-score">
                <span class="score-badge ${getScoreBadgeClass(fact.match_score)}">
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

        ${fact.discrepancies && fact.discrepancies !== 'none' && fact.discrepancies.toLowerCase() !== 'none' ? `
            <div class="fact-discrepancies">
                <div class="fact-discrepancies-label">⚠️ Discrepancies</div>
                ${escapeHtml(fact.discrepancies)}
            </div>
        ` : ''}

        ${fact.reasoning ? `
            <details style="margin-top: 1rem;">
                <summary style="cursor: pointer; font-weight: 600; color: var(--text-secondary); user-select: none;">
                    View Detailed Reasoning
                </summary>
                <div style="margin-top: 0.75rem; padding: 1rem; background: white; border-radius: 6px; border: 1px solid var(--border-color); font-size: 0.95em; line-height: 1.6;">
                    ${escapeHtml(fact.reasoning)}
                </div>
            </details>
        ` : ''}
    `;

    return card;
}

/**
 * Get priority indicator for facts
 */
function getPriorityIndicator(score, index) {
    if (score < 0.5) {
        return '🚨 ';
    } else if (score < 0.7) {
        return '⚠️ ';
    } else if (index < 3) {
        return '📍 ';
    }
    return '';
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
 * Get score badge class (includes critical)
 */
function getScoreBadgeClass(score) {
    if (score >= 0.9) return 'accurate';
    if (score >= 0.7) return 'good';
    if (score >= 0.5) return 'questionable';
    return 'critical';
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
    console.log('Fact Checker initialized - Real-time progress streaming enabled');
    htmlInput.focus();
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

        if (data.pipelines) {
            console.log('Available pipelines:', {
                'LLM Output (with links)': data.pipelines.llm_output,
                'Web Search (plain text)': data.pipelines.web_search
            });
        }

        if (!data.pipelines?.web_search) {
            console.warn('⚠️ Web Search pipeline not available (TAVILY_API_KEY not configured)');
        }
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