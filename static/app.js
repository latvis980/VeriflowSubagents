// static/app.js - Enhanced with mode selection and LLM output verification

// DOM Elements
const htmlInput = document.getElementById('htmlInput');
const checkBtn = document.getElementById('checkBtn');
const clearBtn = document.getElementById('clearBtn');
const stopBtn = document.getElementById('stopBtn');
const publicationField = document.getElementById('publicationField');
const publicationName = document.getElementById('publicationName');

const statusSection = document.getElementById('statusSection');
const resultsSection = document.getElementById('resultsSection');
const errorSection = document.getElementById('errorSection');
const progressLog = document.getElementById('progressLog');

// Mode selection elements
const modeTabs = document.querySelectorAll('.mode-tab');
const llmOutputInstructions = document.getElementById('llmOutputInstructions');
const textFactcheckInstructions = document.getElementById('textFactcheckInstructions');
const biasAnalysisInstructions = document.getElementById('biasAnalysisInstructions');
const inputSectionTitle = document.getElementById('inputSectionTitle');
const inputHelpText = document.getElementById('inputHelpText');
const contentFormatIndicator = document.getElementById('contentFormatIndicator');

// Modal elements
const plainTextModal = document.getElementById('plainTextModal');
const switchToTextMode = document.getElementById('switchToTextMode');
const switchToBiasMode = document.getElementById('switchToBiasMode');
const continueAnyway = document.getElementById('continueAnyway');
const closeModal = document.getElementById('closeModal');

// Tab elements
const factCheckTab = document.getElementById('factCheckTab');
const biasAnalysisTab = document.getElementById('biasAnalysisTab');
const factCheckResults = document.getElementById('factCheckResults');
const biasAnalysisResults = document.getElementById('biasAnalysisResults');

// Model tabs for bias analysis
const modelTabs = document.querySelectorAll('.model-tab');

const factsList = document.getElementById('factsList');
const exportBtn = document.getElementById('exportBtn');
const newCheckBtn = document.getElementById('newCheckBtn');
const retryBtn = document.getElementById('retryBtn');

// State
let currentMode = 'llm-output'; // 'llm-output', 'text-factcheck', 'bias-analysis'
let currentFactCheckResults = null;
let currentBiasResults = null;
let activeEventSources = [];
let currentJobIds = {
    factCheck: null,
    biasCheck: null
};
let pendingContent = null; // Store content when showing modal

// ============================================
// MODE SELECTION
// ============================================

/**
 * Switch between analysis modes
 */
function switchMode(mode) {
    currentMode = mode;

    // Update tab styling
    modeTabs.forEach(tab => {
        tab.classList.toggle('active', tab.dataset.mode === mode);
    });

    // Update instructions visibility
    llmOutputInstructions.style.display = mode === 'llm-output' ? 'block' : 'none';
    textFactcheckInstructions.style.display = mode === 'text-factcheck' ? 'block' : 'none';
    biasAnalysisInstructions.style.display = mode === 'bias-analysis' ? 'block' : 'none';

    // Update input section title and help text
    switch (mode) {
        case 'llm-output':
            inputSectionTitle.textContent = '📋 Paste LLM Output';
            inputHelpText.textContent = 'Copy the full response from ChatGPT/Perplexity using the Copy button';
            htmlInput.placeholder = 'Paste your LLM output here...\n\nCopy the response using the Copy button from ChatGPT or Perplexity.\nThe content should include HTML links to sources.';
            break;
        case 'text-factcheck':
            inputSectionTitle.textContent = '📝 Paste Text to Verify';
            inputHelpText.textContent = 'Paste any text and we\'ll search the web to verify the facts';
            htmlInput.placeholder = 'Paste your text here...\n\nNews articles, social media posts, or any text you want to fact-check.\nWe\'ll search the web to verify the claims.';
            break;
        case 'bias-analysis':
            inputSectionTitle.textContent = '📊 Paste Text for Bias Analysis';
            inputHelpText.textContent = 'Paste any text to analyze for political and ideological bias';
            htmlInput.placeholder = 'Paste your text here...\n\nNews articles, opinion pieces, or any written content.\nWe\'ll analyze it for bias using multiple AI models.';
            break;
    }

    // Show/hide publication field
    publicationField.style.display = mode === 'bias-analysis' ? 'block' : 'none';

    // Update button text
    const btnText = checkBtn.querySelector('.btn-text');
    switch (mode) {
        case 'llm-output':
            btnText.textContent = 'Verify Sources';
            break;
        case 'text-factcheck':
            btnText.textContent = 'Fact-Check Text';
            break;
        case 'bias-analysis':
            btnText.textContent = 'Analyze Bias';
            break;
    }

    // Clear format indicator when switching modes
    hideContentFormatIndicator();
}

// ============================================
// CONTENT DETECTION
// ============================================

/**
 * Check if content contains HTML links
 */
function hasHTMLLinks(content) {
    // Check for <a href="..."> patterns
    const linkPattern = /<\s*a\s+[^>]*href\s*=\s*["'][^"']+["'][^>]*>/i;
    return linkPattern.test(content);
}

/**
 * Check if content has any HTML tags
 */
function hasHTMLTags(content) {
    const htmlPattern = /<\s*[a-z][^>]*>/i;
    return htmlPattern.test(content);
}

/**
 * Count the number of links in content
 */
function countLinks(content) {
    const linkPattern = /<\s*a\s+[^>]*href\s*=\s*["'][^"']+["'][^>]*>/gi;
    const matches = content.match(linkPattern);
    return matches ? matches.length : 0;
}

/**
 * Show content format indicator
 */
function showContentFormatIndicator(hasLinks, linkCount) {
    const indicator = contentFormatIndicator;
    const icon = document.getElementById('formatIcon');
    const message = document.getElementById('formatMessage');

    if (hasLinks) {
        icon.textContent = '✅';
        message.textContent = `Detected ${linkCount} source link${linkCount !== 1 ? 's' : ''} - ready for verification`;
        indicator.className = 'content-format-indicator valid';
    } else {
        icon.textContent = '⚠️';
        message.textContent = 'No source links detected in this content';
        indicator.className = 'content-format-indicator warning';
    }

    indicator.style.display = 'flex';
}

/**
 * Hide content format indicator
 */
function hideContentFormatIndicator() {
    contentFormatIndicator.style.display = 'none';
}

// ============================================
// MODAL HANDLING
// ============================================

/**
 * Show the plain text warning modal
 */
function showPlainTextModal() {
    plainTextModal.style.display = 'flex';
}

/**
 * Hide the plain text warning modal
 */
function hidePlainTextModal() {
    plainTextModal.style.display = 'none';
}

// Modal event listeners
switchToTextMode.addEventListener('click', () => {
    hidePlainTextModal();
    switchMode('text-factcheck');
    // Proceed with the content
    if (pendingContent) {
        processContent(pendingContent, 'text');
        pendingContent = null;
    }
});

switchToBiasMode.addEventListener('click', () => {
    hidePlainTextModal();
    switchMode('bias-analysis');
    // Proceed with bias analysis
    if (pendingContent) {
        processContent(pendingContent, 'bias');
        pendingContent = null;
    }
});

continueAnyway.addEventListener('click', () => {
    hidePlainTextModal();
    // Continue with LLM output mode anyway (will likely fail gracefully)
    if (pendingContent) {
        processContent(pendingContent, 'html');
        pendingContent = null;
    }
});

closeModal.addEventListener('click', () => {
    hidePlainTextModal();
    pendingContent = null;
});

// Close modal on outside click
plainTextModal.addEventListener('click', (e) => {
    if (e.target === plainTextModal) {
        hidePlainTextModal();
        pendingContent = null;
    }
});

// ============================================
// MODE TAB EVENT LISTENERS
// ============================================

modeTabs.forEach(tab => {
    tab.addEventListener('click', () => {
        switchMode(tab.dataset.mode);
    });
});

// ============================================
// INPUT MONITORING
// ============================================

// Monitor input for content format (only in LLM output mode)
htmlInput.addEventListener('input', debounce(() => {
    if (currentMode === 'llm-output') {
        const content = htmlInput.value.trim();
        if (content.length > 50) { // Only check after reasonable input
            const links = hasHTMLLinks(content);
            const linkCount = countLinks(content);
            showContentFormatIndicator(links, linkCount);
        } else {
            hideContentFormatIndicator();
        }
    }
}, 500));

/**
 * Debounce function
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

// ============================================
// MAIN EVENT LISTENERS
// ============================================

checkBtn.addEventListener('click', handleCheckContent);
clearBtn.addEventListener('click', handleClear);
stopBtn.addEventListener('click', handleStopAnalysis);
exportBtn.addEventListener('click', handleExport);
newCheckBtn.addEventListener('click', handleNewCheck);
retryBtn.addEventListener('click', handleRetry);

// Allow Ctrl/Cmd + Enter to submit
htmlInput.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        handleCheckContent();
    }
});

// Result tab switching
factCheckTab.addEventListener('click', () => switchResultTab('fact-check'));
biasAnalysisTab.addEventListener('click', () => switchResultTab('bias-analysis'));

// Model tab switching for bias analysis
modelTabs.forEach(tab => {
    tab.addEventListener('click', () => switchModelTab(tab.dataset.model));
});

/**
 * Switch between result tabs
 */
function switchResultTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });

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
 * Switch between model tabs in bias analysis
 */
function switchModelTab(modelName) {
    modelTabs.forEach(tab => {
        tab.classList.toggle('active', tab.dataset.model === modelName);
    });

    document.querySelectorAll('.model-content').forEach(content => {
        content.classList.remove('active');
    });

    document.getElementById(modelName + 'Analysis').classList.add('active');
}

// ============================================
// MAIN HANDLER
// ============================================

/**
 * Main function to check content
 */
async function handleCheckContent() {
    const content = htmlInput.value.trim();

    if (!content) {
        showError('Please paste some content to analyze.');
        return;
    }

    // Mode-specific validation
    if (currentMode === 'llm-output') {
        const links = hasHTMLLinks(content);

        if (!links) {
            // Show modal to suggest switching modes
            pendingContent = content;
            showPlainTextModal();
            return;
        }

        // Has links, proceed with LLM output pipeline
        processContent(content, 'html');

    } else if (currentMode === 'text-factcheck') {
        // Text mode - proceed with web search pipeline
        processContent(content, 'text');

    } else if (currentMode === 'bias-analysis') {
        // Bias analysis mode
        processContent(content, 'bias');
    }
}

/**
 * Process content based on type
 */
async function processContent(content, type) {
    // Close any existing streams
    closeAllStreams();

    setLoadingState(true);
    stopBtn.disabled = false;
    hideAllSections();
    showSection(statusSection);
    clearProgressLog();

    // Reset results and job IDs
    currentFactCheckResults = null;
    currentBiasResults = null;
    currentJobIds.factCheck = null;
    currentJobIds.biasCheck = null;

    try {
        if (type === 'html' || type === 'text') {
            addProgress(`🔍 Starting fact checking (${type === 'html' ? 'LLM Output' : 'Web Search'} mode)...`);
            await runFactCheck(content, type);
        } else if (type === 'bias') {
            addProgress('📊 Starting bias analysis...');
            await runBiasCheck(content);
        }

        // Display results
        displayCombinedResults(type);

    } catch (error) {
        console.error('Error during analysis:', error);

        if (!error.message.includes('cancelled') && !error.message.includes('stopped')) {
            showError(error.message || 'An unexpected error occurred. Please try again.');
        }
    } finally {
        setLoadingState(false);
        stopBtn.disabled = true;
    }
}

/**
 * Run fact checking pipeline
 */
async function runFactCheck(content, type) {
    try {
        const startResponse = await fetch('/api/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                html_content: content,
                input_type: type // Pass the type to backend
            })
        });

        if (!startResponse.ok) {
            const errorData = await startResponse.json();
            throw new Error(errorData.message || `Fact check error: ${startResponse.status}`);
        }

        const { job_id } = await startResponse.json();
        currentJobIds.factCheck = job_id;
        console.log('Fact check job started:', job_id);

        // Stream progress
        const result = await streamJobProgress(job_id, '🔍');
        currentFactCheckResults = result;
        currentJobIds.factCheck = null;

    } catch (error) {
        currentJobIds.factCheck = null;
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
        currentJobIds.biasCheck = job_id;
        console.log('Bias check job started:', job_id);

        // Stream progress
        const result = await streamJobProgress(job_id, '📊');
        currentBiasResults = result;
        currentJobIds.biasCheck = null;

    } catch (error) {
        currentJobIds.biasCheck = null;
        console.error('Bias check error:', error);
        addProgress('❌ Bias analysis failed: ' + error.message);
        throw error;
    }
}

/**
 * Stream job progress via SSE
 */
function streamJobProgress(jobId, emoji) {
    return new Promise((resolve, reject) => {
        const eventSource = new EventSource(`/api/job/${jobId}/stream`);
        activeEventSources.push(eventSource);

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);

            // Handle completed status
            if (data.status === 'completed') {
                addProgress(emoji + ' Analysis complete!');
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

            // Handle progress items
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
function displayCombinedResults(type) {
    hideAllSections();
    showSection(resultsSection);

    // Show appropriate tabs based on what we have
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
        switchResultTab('fact-check');
    } else if (currentBiasResults) {
        switchResultTab('bias-analysis');
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
        ? (facts.reduce((sum, f) => sum + f.verification_score, 0) / totalFacts) 
        : 0;

    document.getElementById('totalFacts').textContent = totalFacts;
    document.getElementById('accurateFacts').textContent = accurateFacts;
    document.getElementById('goodFacts').textContent = goodFacts;
    document.getElementById('questionableFacts').textContent = questionableFacts;
    document.getElementById('avgScore').textContent = Math.round(avgScore * 100) + '%';

    document.getElementById('sessionId').textContent = sessionId;
    document.getElementById('processingTime').textContent = Math.round(duration) + 's';

    // Show audit link if available
    const auditLink = document.getElementById('auditLink');
    if (data.audit_url) {
        auditLink.href = data.audit_url;
        auditLink.style.display = 'inline';
    } else {
        auditLink.style.display = 'none';
    }

    // Populate facts list
    factsList.innerHTML = '';
    facts.forEach((fact, index) => {
        factsList.appendChild(createFactCard(fact, index + 1));
    });
}

/**
 * Create a fact card element
 */
function createFactCard(fact, number) {
    const card = document.createElement('div');
    card.className = 'fact-card';

    const score = fact.verification_score || 0;
    const scoreClass = score >= 0.9 ? 'accurate' : score >= 0.7 ? 'good' : 'questionable';

    // Get source attribution
    const sourceInfo = getSourceAttribution(fact);

    card.innerHTML = `
        <div class="fact-header">
            <span class="fact-number">#${number}</span>
            <span class="fact-score ${scoreClass}">${Math.round(score * 100)}%</span>
        </div>
        <div class="fact-statement">${escapeHtml(fact.statement)}</div>
        <div class="fact-assessment">${escapeHtml(fact.assessment || 'No assessment available')}</div>
        ${sourceInfo ? `<div class="fact-sources">${sourceInfo}</div>` : ''}
        ${fact.discrepancies ? `<div class="fact-discrepancies"><strong>Discrepancies:</strong> ${escapeHtml(fact.discrepancies)}</div>` : ''}
    `;

    return card;
}

/**
 * Get source attribution for a fact
 */
function getSourceAttribution(fact) {
    if (!fact.sources_used || fact.sources_used.length === 0) {
        return '';
    }

    const sources = fact.sources_used.map(source => {
        const name = source.name || source.url;
        const tier = source.tier ? ` (Tier ${source.tier})` : '';
        return `<span class="source-tag">${escapeHtml(name)}${tier}</span>`;
    }).join(' ');

    return `<strong>Sources:</strong> ${sources}`;
}

/**
 * Display bias analysis results
 */
function displayBiasResults(data) {
    // Update summary scores
    if (data.gpt_analysis) {
        document.getElementById('gptBiasScore').textContent = data.gpt_analysis.bias_score || '-';
        document.getElementById('gptBiasDirection').textContent = data.gpt_analysis.bias_direction || '-';
        document.getElementById('gptOverallAssessment').textContent = data.gpt_analysis.overall_assessment || '-';
        document.getElementById('gptLanguageAnalysis').textContent = data.gpt_analysis.language_analysis || '-';

        const gptIndicators = document.getElementById('gptBiasIndicators');
        gptIndicators.innerHTML = '';
        (data.gpt_analysis.bias_indicators || []).forEach(indicator => {
            const li = document.createElement('li');
            li.textContent = indicator;
            gptIndicators.appendChild(li);
        });
    }

    if (data.claude_analysis) {
        document.getElementById('claudeBiasScore').textContent = data.claude_analysis.bias_score || '-';
        document.getElementById('claudeBiasDirection').textContent = data.claude_analysis.bias_direction || '-';
        document.getElementById('claudeOverallAssessment').textContent = data.claude_analysis.overall_assessment || '-';
        document.getElementById('claudeLanguageAnalysis').textContent = data.claude_analysis.language_analysis || '-';

        const claudeIndicators = document.getElementById('claudeBiasIndicators');
        claudeIndicators.innerHTML = '';
        (data.claude_analysis.bias_indicators || []).forEach(indicator => {
            const li = document.createElement('li');
            li.textContent = indicator;
            claudeIndicators.appendChild(li);
        });
    }

    if (data.consensus) {
        document.getElementById('consensusBiasScore').textContent = data.consensus.consensus_score || '-';
        document.getElementById('consensusBiasDirection').textContent = data.consensus.consensus_direction || '-';
        document.getElementById('finalAssessment').textContent = data.consensus.final_assessment || '-';

        const agreement = document.getElementById('areasOfAgreement');
        agreement.innerHTML = '';
        (data.consensus.areas_of_agreement || []).forEach(area => {
            const li = document.createElement('li');
            li.textContent = area;
            agreement.appendChild(li);
        });

        const disagreement = document.getElementById('areasOfDisagreement');
        disagreement.innerHTML = '';
        (data.consensus.areas_of_disagreement || []).forEach(area => {
            const li = document.createElement('li');
            li.textContent = area;
            disagreement.appendChild(li);
        });

        const recommendations = document.getElementById('recommendations');
        recommendations.innerHTML = '';
        (data.consensus.recommendations || []).forEach(rec => {
            const li = document.createElement('li');
            li.textContent = rec;
            recommendations.appendChild(li);
        });
    }

    // Update session info
    document.getElementById('biasSessionId').textContent = data.session_id || '-';
    document.getElementById('biasProcessingTime').textContent = Math.round(data.processing_time || 0) + 's';
}

// ============================================
// UTILITY FUNCTIONS
// ============================================

function closeAllStreams() {
    activeEventSources.forEach(source => source.close());
    activeEventSources = [];
}

function setLoadingState(loading) {
    checkBtn.disabled = loading;
    const btnText = checkBtn.querySelector('.btn-text');
    const btnLoading = checkBtn.querySelector('.btn-loading');

    if (loading) {
        btnText.style.display = 'none';
        btnLoading.style.display = 'flex';
    } else {
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
    }
}

function hideAllSections() {
    statusSection.style.display = 'none';
    resultsSection.style.display = 'none';
    errorSection.style.display = 'none';
}

function showSection(section) {
    section.style.display = 'block';
}

function clearProgressLog() {
    progressLog.innerHTML = '';
}

function addProgress(message) {
    const entry = document.createElement('div');
    entry.className = 'progress-entry';
    entry.innerHTML = `<span class="timestamp">${new Date().toLocaleTimeString()}</span> ${message}`;
    progressLog.appendChild(entry);
    progressLog.scrollTop = progressLog.scrollHeight;
}

function showError(message) {
    hideAllSections();
    document.getElementById('errorMessage').textContent = message;
    showSection(errorSection);
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function handleClear() {
    htmlInput.value = '';
    hideContentFormatIndicator();
    hideAllSections();
}

function handleNewCheck() {
    htmlInput.value = '';
    hideContentFormatIndicator();
    hideAllSections();
    currentFactCheckResults = null;
    currentBiasResults = null;
}

function handleRetry() {
    hideAllSections();
    handleCheckContent();
}

async function handleStopAnalysis() {
    addProgress('🛑 Stopping analysis...');

    closeAllStreams();

    // Cancel active jobs
    const cancelPromises = [];

    if (currentJobIds.factCheck) {
        cancelPromises.push(
            fetch(`/api/job/${currentJobIds.factCheck}/cancel`, { method: 'POST' })
                .catch(e => console.error('Failed to cancel fact check:', e))
        );
    }

    if (currentJobIds.biasCheck) {
        cancelPromises.push(
            fetch(`/api/job/${currentJobIds.biasCheck}/cancel`, { method: 'POST' })
                .catch(e => console.error('Failed to cancel bias check:', e))
        );
    }

    await Promise.all(cancelPromises);

    setLoadingState(false);
    stopBtn.disabled = true;
    addProgress('✅ Analysis stopped');
}

function handleExport() {
    // Export current results
    const exportData = {
        timestamp: new Date().toISOString(),
        mode: currentMode,
        factCheckResults: currentFactCheckResults,
        biasResults: currentBiasResults
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `analysis-report-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

// Initialize with default mode
switchMode('llm-output');