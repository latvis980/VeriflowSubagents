// static/app.js - Enhanced with module selection and bias analysis

// DOM Elements
const htmlInput = document.getElementById('htmlInput');
const checkBtn = document.getElementById('checkBtn');
const clearBtn = document.getElementById('clearBtn');
const factCheckEnabled = document.getElementById('factCheckEnabled');
const biasCheckEnabled = document.getElementById('biasCheckEnabled');
const publicationField = document.getElementById('publicationField');
const publicationName = document.getElementById('publicationName');

const statusSection = document.getElementById('statusSection');
const resultsSection = document.getElementById('resultsSection');
const errorSection = document.getElementById('errorSection');
const progressLog = document.getElementById('progressLog');

// Tab elements
const factCheckTab = document.getElementById('factCheckTab');
const biasAnalysisTab = document.getElementById('biasAnalysisTab');
const factCheckResults = document.getElementById('factCheckResults');
const biasAnalysisResults = document.getElementById('biasAnalysisResults');

const factsList = document.getElementById('factsList');
const exportBtn = document.getElementById('exportBtn');
const newCheckBtn = document.getElementById('newCheckBtn');
const retryBtn = document.getElementById('retryBtn');

// State
let currentFactCheckResults = null;
let currentBiasResults = null;
let activeEventSources = [];

// Event Listeners
checkBtn.addEventListener('click', handleCheckContent);
clearBtn.addEventListener('click', handleClear);
exportBtn.addEventListener('click', handleExport);
newCheckBtn.addEventListener('click', handleNewCheck);
retryBtn.addEventListener('click', handleRetry);

// Show/hide publication field when bias check is enabled
biasCheckEnabled.addEventListener('change', () => {
    publicationField.style.display = biasCheckEnabled.checked ? 'block' : 'none';
});

// Tab switching
factCheckTab.addEventListener('click', () => switchTab('fact-check'));
biasAnalysisTab.addEventListener('click', () => switchTab('bias-analysis'));

// Allow Ctrl/Cmd + Enter to submit
htmlInput.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        handleCheckContent();
    }
});

/**
 * Switch between result tabs
 */
function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Update content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    
    if (tabName === 'fact-check') {
        factCheckTab.classList.add('active');
        factCheckResults.classList.add('active');
    } else {
        biasAnalysisTab.classList.add('active');
        biasAnalysisResults.classList.add('active');
    }
}

/**
 * Main function to check content
 */
async function handleCheckContent() {
    const content = htmlInput.value.trim();

    if (!content) {
        showError('Please paste some content to analyze.');
        return;
    }

    // Check if at least one module is selected
    const factCheckOn = factCheckEnabled.checked;
    const biasCheckOn = biasCheckEnabled.checked;

    if (!factCheckOn && !biasCheckOn) {
        showError('Please select at least one analysis module (Fact Checking or Bias Analysis).');
        return;
    }

    // Close any existing streams
    closeAllStreams();

    setLoadingState(true);
    hideAllSections();
    showSection(statusSection);
    clearProgressLog();
    
    // Reset results
    currentFactCheckResults = null;
    currentBiasResults = null;

    try {
        // Run selected modules
        const promises = [];

        if (factCheckOn) {
            addProgress('🔍 Starting fact checking...');
            promises.push(runFactCheck(content));
        }

        if (biasCheckOn) {
            addProgress('📊 Starting bias analysis...');
            promises.push(runBiasCheck(content));
        }

        // Wait for all selected modules to complete
        await Promise.all(promises);

        // Display results
        displayCombinedResults();

    } catch (error) {
        console.error('Error during analysis:', error);
        showError(error.message || 'An unexpected error occurred. Please try again.');
    } finally {
        setLoadingState(false);
    }
}

/**
 * Run fact checking pipeline
 */
async function runFactCheck(content) {
    try {
        const startResponse = await fetch('/api/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ html_content: content })
        });

        if (!startResponse.ok) {
            const errorData = await startResponse.json();
            throw new Error(errorData.message || `Fact check error: ${startResponse.status}`);
        }

        const { job_id } = await startResponse.json();
        console.log('Fact check job started:', job_id);

        // Stream progress
        const result = await streamJobProgress(job_id, '🔍');
        currentFactCheckResults = result;

    } catch (error) {
        console.error('Fact check error:', error);
        addProgress('❌ Fact checking failed: ' + error.message);
        throw error;
    }
}

/**
 * Run bias analysis pipeline
 */
async function runBiasCheck(content) {
    try {
        const publication = publicationName.value.trim() || null;
        
        const startResponse = await fetch('/api/check-bias', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                text: content,
                publication_name: publication
            })
        });

        if (!startResponse.ok) {
            const errorData = await startResponse.json();
            throw new Error(errorData.message || `Bias check error: ${startResponse.status}`);
        }

        const { job_id } = await startResponse.json();
        console.log('Bias check job started:', job_id);

        // Stream progress
        const result = await streamJobProgress(job_id, '📊');
        currentBiasResults = result;

    } catch (error) {
        console.error('Bias check error:', error);
        addProgress('❌ Bias analysis failed: ' + error.message);
        throw error;
    }
}

/**
 * Stream job progress using Server-Sent Events
 * FIXED VERSION - handles the actual progress item format from backend
 */
function streamJobProgress(jobId, emoji = '⏳') {
    return new Promise((resolve, reject) => {
        const eventSource = new EventSource(`/api/job/${jobId}/stream`);
        activeEventSources.push(eventSource);

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);

            // Handle heartbeat (no action needed)
            if (data.heartbeat) {
                return;
            }

            // Handle error
            if (data.error) {
                eventSource.close();
                reject(new Error(data.error));
                return;
            }

            // Handle completed status
            if (data.status === 'completed') {
                addProgress('✅ Analysis complete!');
                eventSource.close();
                resolve(data.result);
                return;
            }

            // Handle failed status
            if (data.status === 'failed') {
                eventSource.close();
                reject(new Error(data.error || 'Job failed'));
                return;
            }

            // Handle progress items (the actual format from backend)
            // Progress items have: {timestamp, message, details}
            if (data.message) {
                addProgress(emoji + ' ' + data.message);
            }
        };

        eventSource.onerror = () => {
            eventSource.close();
            reject(new Error('Connection lost during analysis'));
        };
    });
}

/**
 * Display combined results
 */
function displayCombinedResults() {
    hideAllSections();
    showSection(resultsSection);

    // Show appropriate tabs
    if (currentFactCheckResults) {
        factCheckTab.style.display = 'block';
        displayFactCheckResults(currentFactCheckResults);
    } else {
        factCheckTab.style.display = 'none';
    }

    if (currentBiasResults) {
        biasAnalysisTab.style.display = 'block';
        displayBiasResults(currentBiasResults);
    } else {
        biasAnalysisTab.style.display = 'none';
    }

    // Set initial active tab
    if (currentFactCheckResults) {
        switchTab('fact-check');
    } else if (currentBiasResults) {
        switchTab('bias-analysis');
    }
}

/**
 * Display fact check results
 */
function displayFactCheckResults(data) {
    const facts = data.facts || [];
    const sessionId = data.session_id || '-';
    const duration = data.processing_time || 0;

    // Update summary
    const totalFacts = facts.length;
    const accurateFacts = facts.filter(f => f.verification_score >= 0.9).length;
    const goodFacts = facts.filter(f => f.verification_score >= 0.7 && f.verification_score < 0.9).length;
    const questionableFacts = facts.filter(f => f.verification_score < 0.7).length;
    const avgScore = totalFacts > 0 
        ? (facts.reduce((sum, f) => sum + f.verification_score, 0) / totalFacts).toFixed(2)
        : '0.00';

    document.getElementById('totalFacts').textContent = totalFacts;
    document.getElementById('accurateFacts').textContent = accurateFacts;
    document.getElementById('goodFacts').textContent = goodFacts;
    document.getElementById('questionableFacts').textContent = questionableFacts;
    document.getElementById('avgScore').textContent = avgScore;
    document.getElementById('sessionId').textContent = sessionId;
    document.getElementById('duration').textContent = duration.toFixed(1) + 's';

    // Display facts
    factsList.innerHTML = '';
    facts.forEach((fact, index) => {
        const card = createFactCard(fact, index);
        factsList.appendChild(card);
    });

    // LangSmith URL
    if (data.langsmith_url) {
        document.getElementById('langsmithUrl').href = data.langsmith_url;
    }
}

/**
 * Create fact card element
 */
function createFactCard(fact, index) {
    const card = document.createElement('div');
    card.className = `fact-card ${getScoreBadgeClass(fact.verification_score)}`;

    const scoreEmoji = getScoreEmoji(fact.verification_score);
    const priorityIndicator = getPriorityIndicator(fact.verification_score, index);

    card.innerHTML = `
        <div class="fact-header">
            <span class="fact-id">${priorityIndicator}Fact #${fact.id}</span>
            <span class="score-badge ${getScoreBadgeClass(fact.verification_score)}">
                ${scoreEmoji} Score: ${fact.verification_score.toFixed(2)}
            </span>
        </div>

        <div class="fact-statement">
            ${escapeHtml(fact.statement)}
        </div>

        ${fact.assessment ? `
            <div class="fact-assessment">
                <strong>Assessment:</strong> ${escapeHtml(fact.assessment)}
            </div>
        ` : ''}

        ${fact.sources && fact.sources.length > 0 ? `
            <div class="fact-sources">
                <h4>📚 Sources:</h4>
                <ul class="source-list">
                    ${fact.sources.map(source => `
                        <li class="source-item">
                            <a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer">
                                ${escapeHtml(source.title || source.url)}
                            </a>
                        </li>
                    `).join('')}
                </ul>
            </div>
        ` : ''}

        ${fact.discrepancies ? `
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
 * Display bias analysis results
 */
function displayBiasResults(data) {
    const combined = data.combined_report || {};
    const gpt = data.gpt_analysis || {};
    const claude = data.claude_analysis || {};
    const publication = data.publication_profile || null;

    // Summary
    document.getElementById('consensusBiasScore').textContent = (combined.consensus_bias_score || 0).toFixed(1);
    document.getElementById('biasDirection').textContent = combined.consensus_direction || 'Unknown';
    document.getElementById('biasConfidence').textContent = 
        ((combined.confidence || 0) * 100).toFixed(0) + '%';

    // Publication context
    if (publication) {
        const pubContext = document.getElementById('publicationContext');
        pubContext.style.display = 'block';
        document.getElementById('publicationInfo').innerHTML = `
            <p><strong>Name:</strong> ${escapeHtml(publication.name)}</p>
            <p><strong>Political Leaning:</strong> ${escapeHtml(publication.political_leaning)}</p>
            <p><strong>Known Bias Rating:</strong> ${publication.bias_rating}/10</p>
            ${publication.ownership ? `<p><strong>Ownership:</strong> ${escapeHtml(publication.ownership)}</p>` : ''}
            ${publication.credibility_notes ? `<p><strong>Notes:</strong> ${escapeHtml(publication.credibility_notes)}</p>` : ''}
        `;
    }

    // Model analyses
    document.getElementById('gptBiasScore').textContent = (gpt.overall_bias_score || 0).toFixed(1);
    document.getElementById('gptDirection').textContent = gpt.primary_bias_direction || 'Unknown';
    
    document.getElementById('claudeBiasScore').textContent = (claude.overall_bias_score || 0).toFixed(1);
    document.getElementById('claudeDirection').textContent = claude.primary_bias_direction || 'Unknown';

    // Display biases detected by each model
    displayModelBiases('gptBiases', gpt.biases_detected || []);
    displayModelBiases('claudeBiases', claude.biases_detected || []);

    // Combined assessment
    displayList('areasOfAgreement', combined.areas_of_agreement || []);
    displayList('areasOfDisagreement', combined.areas_of_disagreement || []);
    
    document.getElementById('finalAssessment').textContent = combined.final_assessment || 'No assessment available.';
    
    displayList('recommendations', combined.recommendations || []);

    // Session info
    document.getElementById('biasSessionId').textContent = data.session_id || '-';
    document.getElementById('biasProcessingTime').textContent = 
        (data.processing_time || 0).toFixed(1) + 's';
}

/**
 * Display model-specific biases
 */
function displayModelBiases(elementId, biases) {
    const container = document.getElementById(elementId);
    if (!biases || biases.length === 0) {
        container.innerHTML = '<p style="color: var(--text-secondary); font-size: 0.9rem;">No significant biases detected</p>';
        return;
    }

    container.innerHTML = biases.map(bias => `
        <div class="bias-instance">
            <div class="bias-instance-type">
                ${escapeHtml(bias.type)} - ${escapeHtml(bias.direction)}
            </div>
            <div class="bias-instance-severity">
                Severity: ${bias.severity}/10
            </div>
            <div style="margin-top: 0.5rem; font-size: 0.9rem;">
                ${escapeHtml(bias.evidence)}
            </div>
        </div>
    `).join('');
}

/**
 * Display a list in the bias assessment
 */
function displayList(elementId, items) {
    const ul = document.getElementById(elementId);
    
    if (!items || items.length === 0) {
        ul.innerHTML = '<li style="background: transparent; border: none; color: var(--text-secondary);">None noted</li>';
        return;
    }

    ul.innerHTML = items.map(item => `
        <li>${escapeHtml(item)}</li>
    `).join('');
}

/**
 * Progress log helpers
 */
function clearProgressLog() {
    progressLog.innerHTML = '';
}

function addProgress(message) {
    const item = document.createElement('div');
    item.className = 'progress-item';
    item.textContent = message;
    progressLog.appendChild(item);
    
    // Auto-scroll to latest
    progressLog.scrollTop = progressLog.scrollHeight;
}

/**
 * Helper functions
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getPriorityIndicator(score, index) {
    if (score < 0.5) return '🚨 ';
    if (score < 0.7) return '⚠️ ';
    if (index < 3) return '📍 ';
    return '';
}

function getScoreClass(score) {
    if (score >= 0.9) return 'accurate';
    if (score >= 0.7) return 'good';
    return 'questionable';
}

function getScoreBadgeClass(score) {
    if (score >= 0.9) return 'accurate';
    if (score >= 0.7) return 'good';
    if (score >= 0.5) return 'questionable';
    return 'critical';
}

function getScoreEmoji(score) {
    if (score >= 0.9) return '✅';
    if (score >= 0.7) return '⚠️';
    return '❌';
}

function closeAllStreams() {
    activeEventSources.forEach(source => source.close());
    activeEventSources = [];
}

function hideAllSections() {
    statusSection.style.display = 'none';
    resultsSection.style.display = 'none';
    errorSection.style.display = 'none';
}

function showSection(section) {
    section.style.display = 'block';
}

function showError(message) {
    hideAllSections();
    showSection(errorSection);
    document.getElementById('errorMessage').textContent = message;
}

function setLoadingState(isLoading) {
    checkBtn.disabled = isLoading;
    const btnText = checkBtn.querySelector('.btn-text');
    const btnLoading = checkBtn.querySelector('.btn-loading');

    if (isLoading) {
        btnText.style.display = 'none';
        btnLoading.style.display = 'flex';
    } else {
        btnText.style.display = 'block';
        btnLoading.style.display = 'none';
    }
}

function handleClear() {
    htmlInput.value = '';
    publicationName.value = '';
    htmlInput.focus();
}

function handleNewCheck() {
    hideAllSections();
    htmlInput.value = '';
    publicationName.value = '';
    htmlInput.focus();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function handleRetry() {
    hideAllSections();
    htmlInput.focus();
}

function handleExport() {
    const exportData = {
        timestamp: new Date().toISOString(),
        fact_check: currentFactCheckResults,
        bias_analysis: currentBiasResults
    };

    const dataStr = JSON.stringify(exportData, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);

    const link = document.createElement('a');
    link.href = url;
    link.download = `analysis-report-${Date.now()}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}
