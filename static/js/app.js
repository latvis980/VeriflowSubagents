// static/js/app.js - Main Application Entry Point
// This file ties together all modules and sets up event listeners

// ============================================
// URL INPUT ELEMENTS
// ============================================

const articleUrl = document.getElementById('articleUrl');
const fetchUrlBtn = document.getElementById('fetchUrlBtn');
const urlFetchStatus = document.getElementById('urlFetchStatus');

// Store the last fetched article data (including metadata & credibility)
let lastFetchedArticle = null;

// ============================================
// URL INPUT HANDLING
// ============================================

// Validate URL format
function isValidUrl(string) {
    try {
        const url = new URL(string);
        return url.protocol === 'http:' || url.protocol === 'https:';
    } catch (_) {
        return false;
    }
}

// Show URL fetch status with different states
function showUrlStatus(type, message, details = null) {
    if (!urlFetchStatus) return;
    urlFetchStatus.style.display = 'flex';
    urlFetchStatus.className = `url-fetch-status ${type}`;

    const icons = {
        loading: '⏳',
        success: '✅',
        error: '❌',
        info: 'ℹ️'
    };

    let html = `
        <span class="status-icon">${icons[type] || '📄'}</span>
        <span class="status-text">${message}</span>
    `;

    // Add credibility badge if available
    if (details && details.credibility) {
        const tierColors = {
            1: '#22c55e',  // green
            2: '#84cc16',  // lime
            3: '#eab308',  // yellow
            4: '#f97316',  // orange
            5: '#ef4444'   // red
        };
        const tier = details.credibility.tier || 3;
        const color = tierColors[tier] || '#6b7280';

        html += `
            <span class="credibility-badge" style="
                background: ${color}20;
                color: ${color};
                padding: 2px 8px;
                border-radius: 12px;
                font-size: 0.75rem;
                font-weight: 600;
                margin-left: 8px;
            ">Tier ${tier}</span>
        `;
    }

    urlFetchStatus.innerHTML = html;
}

function hideUrlStatus() {
    if (urlFetchStatus) {
        urlFetchStatus.style.display = 'none';
    }
}

// ============================================
// JOB-BASED URL FETCHING
// ============================================

/**
 * Poll for job completion
 * @param {string} jobId - The job ID to poll
 * @param {function} onProgress - Callback for progress updates
 * @param {number} maxWaitMs - Maximum time to wait (default 120 seconds)
 * @returns {Promise<object>} - The job result
 */
async function pollJobCompletion(jobId, onProgress = null, maxWaitMs = 120000) {
    const startTime = Date.now();
    const pollInterval = 1000; // 1 second

    while (Date.now() - startTime < maxWaitMs) {
        try {
            const response = await fetch(`/api/job/${jobId}`);
            const job = await response.json();

            if (job.error && !job.status) {
                throw new Error(job.error);
            }

            // Call progress callback if provided
            if (onProgress && job.progress_log && job.progress_log.length > 0) {
                const lastProgress = job.progress_log[job.progress_log.length - 1];
                onProgress(lastProgress);
            }

            if (job.status === 'completed') {
                return job.result;
            }

            if (job.status === 'failed') {
                throw new Error(job.error || 'Job failed');
            }

            if (job.status === 'cancelled') {
                throw new Error('Job was cancelled');
            }

            // Wait before next poll
            await new Promise(resolve => setTimeout(resolve, pollInterval));

        } catch (error) {
            if (error.message.includes('Job not found')) {
                throw new Error('Job expired or not found');
            }
            throw error;
        }
    }

    throw new Error('Timeout waiting for job completion');
}

/**
 * Fetch article content from URL via backend (JOB-BASED VERSION)
 * Returns enriched data including metadata and credibility
 * 
 * @param {string} url - The URL to fetch
 * @param {object} options - Optional settings
 * @returns {Promise<object>} - Enriched article data
 */
async function fetchArticleFromUrl(url, options = {}) {
    const {
        extractMetadata = true,
        checkCredibility = true,
        runMbfcIfMissing = true
    } = options;

    showUrlStatus('loading', 'Starting article fetch...');

    try {
        // Step 1: Start the scrape job
        const startResponse = await fetch('/api/scrape-url', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                url: url,
                extract_metadata: extractMetadata,
                check_credibility: checkCredibility,
                run_mbfc_if_missing: runMbfcIfMissing
            })
        });

        if (!startResponse.ok) {
            const error = await startResponse.json();
            throw new Error(error.error || error.message || 'Failed to start fetch');
        }

        const startData = await startResponse.json();
        const jobId = startData.job_id;

        if (!jobId) {
            throw new Error('No job ID returned');
        }

        showUrlStatus('loading', 'Scraping article content...');

        // Step 2: Poll for completion with progress updates
        const result = await pollJobCompletion(jobId, (progress) => {
            if (progress && progress.message) {
                showUrlStatus('loading', progress.message);
            }
        });

        // Step 3: Validate result
        if (!result.success) {
            throw new Error(result.error || 'Failed to fetch article');
        }

        if (!result.content || result.content.trim().length < 100) {
            throw new Error('Could not extract sufficient content from the URL');
        }

        // Store the full result for later use
        lastFetchedArticle = result;

        // Build success message
        const charCount = result.content_length.toLocaleString();
        let successMsg = `Fetched ${charCount} characters`;

        if (result.title) {
            successMsg += ` from "${result.title.substring(0, 40)}${result.title.length > 40 ? '...' : ''}"`;
        }

        if (result.author) {
            successMsg += ` by ${result.author}`;
        }

        showUrlStatus('success', successMsg, result);

        // Display metadata card if we have rich data
        if (result.title || result.author || result.publication_date || result.credibility) {
            displayArticleMetadata(result);
        }

        return {
            content: result.content,
            title: result.title,
            url: result.url,
            // Include all the enriched data
            metadata: {
                author: result.author,
                publicationDate: result.publication_date,
                publicationDateRaw: result.publication_date_raw,
                publicationName: result.publication_name,
                articleType: result.article_type,
                section: result.section,
                confidence: result.metadata_confidence
            },
            credibility: result.credibility,
            domain: result.domain
        };

    } catch (error) {
        showUrlStatus('error', error.message);
        throw error;
    }
}

// ============================================
// ARTICLE METADATA DISPLAY
// ============================================

/**
 * Display article metadata card below the URL input
 * @param {object} article - The enriched article data
 */
function displayArticleMetadata(article) {
    // Remove existing metadata card if any
    const existingCard = document.getElementById('articleMetadataCard');
    if (existingCard) {
        existingCard.remove();
    }

    // Don't show if no meaningful metadata
    if (!article.title && !article.author && !article.credibility) {
        return;
    }

    const card = document.createElement('div');
    card.id = 'articleMetadataCard';
    card.className = 'article-metadata-card';

    // Build card content
    let html = '<div class="metadata-header">';

    // Credibility tier badge
    if (article.credibility) {
        const tier = article.credibility.tier || 3;
        const tierColors = {
            1: { bg: '#dcfce7', text: '#166534', border: '#86efac' },
            2: { bg: '#ecfccb', text: '#3f6212', border: '#bef264' },
            3: { bg: '#fef9c3', text: '#854d0e', border: '#fde047' },
            4: { bg: '#ffedd5', text: '#9a3412', border: '#fdba74' },
            5: { bg: '#fee2e2', text: '#991b1b', border: '#fca5a5' }
        };
        const colors = tierColors[tier] || tierColors[3];

        html += `
            <div class="credibility-tier-badge" style="
                background: ${colors.bg};
                color: ${colors.text};
                border: 1px solid ${colors.border};
                padding: 4px 12px;
                border-radius: 16px;
                font-weight: 600;
                font-size: 0.85rem;
            ">
                Tier ${tier} ${getCredibilityEmoji(tier)}
            </div>
        `;
    }

    html += '</div>';

    // Article info
    html += '<div class="metadata-body">';

    if (article.title) {
        html += `<h4 class="metadata-title">${escapeHtml(article.title)}</h4>`;
    }

    html += '<div class="metadata-details">';

    if (article.publication_name || article.domain) {
        html += `
            <span class="metadata-item">
                <span class="metadata-icon">📰</span>
                ${escapeHtml(article.publication_name || article.domain)}
            </span>
        `;
    }

    if (article.author) {
        html += `
            <span class="metadata-item">
                <span class="metadata-icon">✍️</span>
                ${escapeHtml(article.author)}
            </span>
        `;
    }

    if (article.publication_date) {
        const dateStr = formatDate(article.publication_date);
        html += `
            <span class="metadata-item">
                <span class="metadata-icon">📅</span>
                ${dateStr}
            </span>
        `;
    }

    html += '</div>'; // metadata-details

    // Credibility details (collapsible)
    if (article.credibility && article.credibility.source !== 'fallback') {
        html += `
            <details class="credibility-details">
                <summary>View credibility details</summary>
                <div class="credibility-info">
                    ${article.credibility.rating ? `<div><strong>Rating:</strong> ${article.credibility.rating}</div>` : ''}
                    ${article.credibility.bias_rating ? `<div><strong>Bias:</strong> ${article.credibility.bias_rating}</div>` : ''}
                    ${article.credibility.factual_reporting ? `<div><strong>Factual:</strong> ${article.credibility.factual_reporting}</div>` : ''}
                    ${article.credibility.tier_description ? `<div class="tier-desc">${article.credibility.tier_description}</div>` : ''}
                    ${article.credibility.mbfc_url ? `<a href="${article.credibility.mbfc_url}" target="_blank" class="mbfc-link">View on MBFC →</a>` : ''}
                </div>
            </details>
        `;
    }

    html += '</div>'; // metadata-body

    card.innerHTML = html;

    // Insert after URL fetch status
    const urlStatusElement = document.getElementById('urlFetchStatus');
    if (urlStatusElement && urlStatusElement.parentNode) {
        urlStatusElement.parentNode.insertBefore(card, urlStatusElement.nextSibling);
    }
}

/**
 * Get emoji for credibility tier
 */
function getCredibilityEmoji(tier) {
    const emojis = {
        1: '🏆',
        2: '✅',
        3: '⚠️',
        4: '🔶',
        5: '🚫'
    };
    return emojis[tier] || '❓';
}

/**
 * Format ISO date to readable string
 */
function formatDate(isoDate) {
    if (!isoDate) return '';
    try {
        const date = new Date(isoDate);
        return date.toLocaleDateString('en-US', { 
            year: 'numeric', 
            month: 'short', 
            day: 'numeric' 
        });
    } catch {
        return isoDate;
    }
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================
// URL INPUT LISTENERS INITIALIZATION
// ============================================

function initUrlInputListeners() {
    if (!articleUrl || !fetchUrlBtn) {
        console.log('URL input elements not found, skipping URL input initialization');
        return;
    }

    // Enable/disable fetch button based on URL validity
    articleUrl.addEventListener('input', () => {
        const url = articleUrl.value.trim();
        fetchUrlBtn.disabled = !isValidUrl(url);

        // Add visual indicator when URL is entered
        if (url && isValidUrl(url)) {
            htmlInput.classList.add('url-filled');
        } else {
            htmlInput.classList.remove('url-filled');
        }
    });

    // Clear URL styling when textarea is used directly
    htmlInput.addEventListener('input', () => {
        if (htmlInput.value.trim()) {
            htmlInput.classList.remove('url-filled');
        }
    });

    // Fetch button click handler
    fetchUrlBtn.addEventListener('click', async () => {
        const url = articleUrl.value.trim();

        if (!isValidUrl(url)) {
            showUrlStatus('error', 'Please enter a valid URL');
            return;
        }

        try {
            // Disable button and show loading state
            fetchUrlBtn.disabled = true;
            fetchUrlBtn.innerHTML = '<span class="fetch-icon">⏳</span><span class="fetch-text">Fetching...</span>';

            const result = await fetchArticleFromUrl(url);

            // Put the fetched content into the textarea
            htmlInput.value = result.content;
            htmlInput.classList.add('url-filled');

            // Trigger input event to update any format detection
            htmlInput.dispatchEvent(new Event('input'));

        } catch (error) {
            console.error('URL fetch error:', error);
            // Error already shown via showUrlStatus
        } finally {
            // Re-enable button with original text
            fetchUrlBtn.disabled = !isValidUrl(articleUrl.value.trim());
            fetchUrlBtn.innerHTML = '<span class="fetch-icon">📥</span><span class="fetch-text">Fetch</span>';
        }
    });

    // Allow Enter key to trigger fetch
    articleUrl.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !fetchUrlBtn.disabled) {
            e.preventDefault();
            fetchUrlBtn.click();
        }
    });

    console.log('✅ URL input listeners initialized');
}

// ============================================
// CLEAR URL INPUT
// ============================================

function clearUrlInput() {
    if (articleUrl) {
        articleUrl.value = '';
    }
    if (fetchUrlBtn) {
        fetchUrlBtn.disabled = true;
    }
    hideUrlStatus();
    htmlInput.classList.remove('url-filled');

    // Remove metadata card
    const metadataCard = document.getElementById('articleMetadataCard');
    if (metadataCard) {
        metadataCard.remove();
    }

    // Clear stored article data
    lastFetchedArticle = null;
}

// ============================================
// HELPER: Get last fetched article data
// ============================================

/**
 * Get the credibility data from the last fetched article
 * Useful for passing to analysis endpoints
 */
function getLastFetchedCredibility() {
    return lastFetchedArticle?.credibility || null;
}

/**
 * Get the full last fetched article data
 */
function getLastFetchedArticle() {
    return lastFetchedArticle;
}

// ============================================
// ANALYZE BUTTON HANDLER
// ============================================

async function handleAnalyze() {
    let content = htmlInput.value.trim();
    const url = articleUrl ? articleUrl.value.trim() : '';

    // If URL is provided but content is empty, fetch from URL first
    if (url && isValidUrl(url) && !content) {
        try {
            addProgress('🔗 Fetching article from URL...');
            const result = await fetchArticleFromUrl(url);
            content = result.content;
            htmlInput.value = content;
        } catch (error) {
            showError('Failed to fetch article: ' + error.message);
            return;
        }
    }

    if (!content) {
        showError('Please paste some content or enter a URL to analyze.');
        return;
    }

    // Hide URL status when starting analysis
    hideUrlStatus();

    // Mode-specific validation
    if (AppState.currentMode === 'llm-output') {
        const links = hasHTMLLinks(content);

        if (!links) {
            AppState.pendingContent = content;
            showPlainTextModal();
            return;
        }

        processContent(content, 'html');

    } else if (AppState.currentMode === 'text-factcheck') {
        processContent(content, 'text');

    } else if (AppState.currentMode === 'key-claims') {
        processContent(content, 'key-claims');

    } else if (AppState.currentMode === 'bias-analysis') {
        processContent(content, 'bias');

    } else if (AppState.currentMode === 'lie-detection') {
        processContent(content, 'lie-detection');

    } else if (AppState.currentMode === 'manipulation') {
        processContent(content, 'manipulation');
    }
}

// ============================================
// PROCESS CONTENT
// ============================================

async function processContent(content, type) {
    AppState.closeAllStreams();

    setLoadingState(true);
    stopBtn.disabled = false;
    hideAllSections();
    showSection(statusSection);
    clearProgressLog();

    // Clear all results
    AppState.clearResults();

    try {
        if (type === 'html') {
            // LLM Output Verification Pipeline
            addProgress('🔍 Starting LLM interpretation verification...');
            await runLLMVerification(content);
        } else if (type === 'text') {
            // Web Search Fact-Checking Pipeline
            addProgress('🔍 Starting web search fact-checking...');
            await runFactCheck(content);
        } else if (type === 'key-claims') {
            // Key Claims Pipeline
            addProgress('🎯 Starting key claims analysis...');
            await runKeyClaimsCheck(content);
        } else if (type === 'bias') {
            addProgress('📊 Starting bias analysis...');
            await runBiasCheck(content);
        } else if (type === 'lie-detection') {
            addProgress('🕵️ Starting lie detection analysis...');
            await runLieDetection(content);
        } else if (type === 'manipulation') {
            addProgress('🎭 Starting manipulation analysis...');
            await runManipulationCheck(content);
        }

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

// ============================================
// DISPLAY COMBINED RESULTS
// ============================================

function displayCombinedResults(type) {
    hideAllSections();
    showSection(resultsSection);

    // Hide all result tabs first
    factCheckTab.style.display = 'none';
    if (keyClaimsTab) keyClaimsTab.style.display = 'none';
    biasAnalysisTab.style.display = 'none';
    lieDetectionTab.style.display = 'none';
    if (manipulationTab) manipulationTab.style.display = 'none';

    switch (type) {
        case 'html':
        case 'text':
            // Fact checking results
            factCheckTab.style.display = 'block';
            displayFactCheckResults();
            switchResultTab('fact-check');
            break;

        case 'key-claims':
            // Key claims results
            if (keyClaimsTab) keyClaimsTab.style.display = 'block';
            displayKeyClaimsResults();
            switchResultTab('key-claims');
            break;

        case 'bias':
            // Bias analysis results
            biasAnalysisTab.style.display = 'block';
            displayBiasResults();
            switchResultTab('bias-analysis');
            break;

        case 'lie-detection':
            // Lie Detection
            lieDetectionTab.style.display = 'block';
            displayLieDetectionResults();
            switchResultTab('lie-detection');
            break;

        case 'manipulation':
            // Manipulation Detection
            if (manipulationTab) manipulationTab.style.display = 'block';
            displayManipulationResults();
            switchResultTab('manipulation');
            break;

        default:
            console.error('Unknown result type:', type);
    }
}

// ============================================
// EVENT LISTENERS SETUP
// ============================================

function initEventListeners() {
    // Analyze button
    checkBtn.addEventListener('click', handleAnalyze);

    // Mode tabs
    modeTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            switchMode(tab.dataset.mode);
        });
    });

    // Input validation
    htmlInput.addEventListener('input', () => {
        const content = htmlInput.value.trim();

        if (!content) {
            hideContentFormatIndicator();
            return;
        }

        // Only show format indicator for LLM output mode
        if (AppState.currentMode === 'llm-output') {
            const hasLinks = hasHTMLLinks(content);
            const linkCount = countLinks(content);
            showContentFormatIndicator(hasLinks, linkCount);
        } else {
            hideContentFormatIndicator();
        }
    });

    // Clear button
    clearBtn.addEventListener('click', () => {
        htmlInput.value = '';
        publicationUrl.value = '';
        clearUrlInput();  // Clear URL input and metadata
        hideContentFormatIndicator();
        hideAllSections();
        AppState.clearResults();
    });

    // Stop button
    stopBtn.addEventListener('click', () => {
        AppState.closeAllStreams();
        addProgress('⏹️ Analysis stopped by user', 'warning');
        setLoadingState(false);
        stopBtn.disabled = true;
    });

    // New check button
    newCheckBtn.addEventListener('click', () => {
        hideAllSections();
        htmlInput.value = '';
        publicationUrl.value = '';
        clearUrlInput();  // Clear URL input and metadata
        hideContentFormatIndicator();
        AppState.clearResults();
    });

    // Retry button
    retryBtn.addEventListener('click', () => {
        hideAllSections();
        if (htmlInput.value.trim()) {
            handleAnalyze();
        }
    });

    // Export button
    exportBtn.addEventListener('click', exportResults);
}

// ============================================
// INITIALIZATION
// ============================================

function init() {
    initEventListeners();
    initUrlInputListeners();  // Initialize URL input with metadata support
    initModalListeners();
    initBiasModelTabs();

    console.log('✅ VeriFlow app initialized successfully');
    console.log('📦 Modules loaded: config, utils, ui, modal, api, renderers');
    console.log('🔗 URL fetching with metadata & credibility support enabled');
}

// Run initialization when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}