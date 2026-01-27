// static/js/ui.js - UI State Management
// VeriFlow Redesign - Minimalist Theme

// ============================================
// LOADING STATE
// ============================================

function setLoadingState(isLoading) {
    if (checkBtn) checkBtn.disabled = isLoading;
    if (clearBtn) clearBtn.disabled = isLoading;
    if (htmlInput) htmlInput.disabled = isLoading;
    if (stopBtn) stopBtn.style.display = isLoading ? 'inline-flex' : 'none';
}

// ============================================
// SECTION VISIBILITY
// ============================================

function hideAllSections() {
    if (statusSection) statusSection.style.display = 'none';
    if (resultsSection) resultsSection.style.display = 'none';
    if (errorSection) errorSection.style.display = 'none';
}

function showSection(section) {
    if (section) section.style.display = 'block';
}

function showError(message) {
    hideAllSections();
    showSection(errorSection);
    const errorMsg = document.getElementById('errorMessage');
    if (errorMsg) errorMsg.textContent = message;
}

// ============================================
// PROGRESS LOG
// ============================================

function clearProgressLog() {
    if (progressLog) progressLog.innerHTML = '';
}

function addProgress(message, type = 'info') {
    if (!progressLog) return;

    const entry = document.createElement('div');
    entry.className = `progress-item ${type}`;

    entry.textContent = message;

    progressLog.appendChild(entry);
    progressLog.scrollTop = progressLog.scrollHeight;
}

// ============================================
// CONTENT FORMAT INDICATOR
// ============================================

function showContentFormatIndicator(hasLinks, linkCount) {
    if (!contentFormatIndicator) return;

    const formatIcon = contentFormatIndicator.querySelector('.format-icon');
    const formatText = contentFormatIndicator.querySelector('.format-text');

    if (hasLinks) {
        if (formatIcon) formatIcon.textContent = '✓';
        if (formatText) formatText.textContent = `Detected ${linkCount} source link${linkCount !== 1 ? 's' : ''}`;
        contentFormatIndicator.className = 'content-format-indicator valid';
    } else {
        if (formatIcon) formatIcon.textContent = '!';
        if (formatText) formatText.textContent = 'No source links detected';
        contentFormatIndicator.className = 'content-format-indicator warning';
    }

    contentFormatIndicator.style.display = 'flex';
}

function hideContentFormatIndicator() {
    if (contentFormatIndicator) {
        contentFormatIndicator.style.display = 'none';
    }
}

// ============================================
// MODE SWITCHING
// ============================================

function switchMode(mode) {
    AppState.currentMode = mode;

    // Update card styling
    modeCards.forEach(card => {
        card.classList.toggle('active', card.dataset.mode === mode);
    });

    // Update placeholder text
    updatePlaceholder(mode);

    // Hide content format indicator when switching modes
    hideContentFormatIndicator();

    // Hide URL toggle button for LLM output mode only (copy-paste only)
    // Comprehensive mode CAN use URL input for source verification
    if (toggleUrlBtn) {
        toggleUrlBtn.style.display = (mode === 'llm-output') ? 'none' : '';
    }

    // Show/hide mode-specific instructions
    updateModeInstructions(mode);

    // Ensure text input is shown when switching modes (reset to default)
    showTextInput();

    console.log('Mode switched to:', mode);
}

function updatePlaceholder(mode) {
    if (!htmlInput) return;

    const placeholders = {
        'comprehensive': 'Paste any article, text, or AI-generated content for full analysis...',
        'key-claims': 'Paste the article or text you want to analyze...',
        'bias-analysis': 'Paste the article or text to analyze for bias...',
        'lie-detection': 'Paste the text to analyze for deception markers...',
        'manipulation': 'Paste the article to check for manipulation...',
        'text-factcheck': 'Paste the article or text you want to fact-check...',
        'llm-output': 'Paste AI-generated content with source links (from ChatGPT, Perplexity, etc.)...'
    };

    htmlInput.placeholder = placeholders[mode] || 'Paste content to analyze...';
}

function updateModeInstructions(mode) {
    // Hide all instruction sections
    const allInstructions = document.querySelectorAll('.mode-instructions');
    allInstructions.forEach(el => el.style.display = 'none');

    // Show the relevant instruction section
    const instructionMap = {
        'comprehensive': 'comprehensiveInstructions',
        'key-claims': 'keyClaimsInstructions',
        'bias-analysis': 'biasAnalysisInstructions',
        'lie-detection': 'lieDetectionInstructions',
        'manipulation': 'manipulationInstructions',
        'llm-output': 'llmOutputInstructions',
        'text-factcheck': 'textFactcheckInstructions'
    };

    const instructionId = instructionMap[mode];
    if (instructionId) {
        const el = document.getElementById(instructionId);
        if (el) el.style.display = 'block';
    }

    // Update input section labels
    updateInputLabels(mode);
}

function updateInputLabels(mode) {
    const inputSectionTitle = document.querySelector('.input-label');
    const publicationField = document.getElementById('publicationField');

    // Define labels for each mode
    const modeLabels = {
        'comprehensive': {
            title: 'Content to Analyze',
            showPublication: false
        },
        'key-claims': {
            title: 'Paste Text for Key Claims Analysis',
            showPublication: false
        },
        'bias-analysis': {
            title: 'Paste Text to Analyze for Bias',
            showPublication: true
        },
        'lie-detection': {
            title: 'Paste Article or Text to Analyze',
            showPublication: false
        },
        'manipulation': {
            title: 'Paste Article to Check for Manipulation',
            showPublication: false
        },
        'llm-output': {
            title: 'Paste LLM Output with Sources',
            showPublication: false
        },
        'text-factcheck': {
            title: 'Paste Text to Fact-Check',
            showPublication: false
        }
    };

    const config = modeLabels[mode] || { title: 'Content to Analyze', showPublication: false };

    if (inputSectionTitle) {
        inputSectionTitle.textContent = config.title;
    }

    if (publicationField) {
        publicationField.style.display = config.showPublication ? 'block' : 'none';
    }
}

// ============================================
// RESULTS TAB SWITCHING
// ============================================

function switchResultTab(tabName) {
    const tabMappings = {
        'fact-check': { tab: factCheckTab, panel: factCheckResults },
        'key-claims': { tab: keyClaimsTab, panel: keyClaimsResults },
        'bias-analysis': { tab: biasAnalysisTab, panel: biasAnalysisResults },
        'lie-detection': { tab: lieDetectionTab, panel: lieDetectionResults },
        'manipulation': { tab: manipulationTab, panel: manipulationResults },
        'comprehensive': { tab: comprehensiveTab, panel: comprehensiveResults }
    };

    Object.values(tabMappings).forEach(({ tab, panel }) => {
        if (tab) tab.classList.remove('active');
        if (panel) {
            panel.style.display = 'none';
            panel.classList.remove('active');
        }
    });

    const selected = tabMappings[tabName];
    if (selected) {
        if (selected.tab) selected.tab.classList.add('active');
        if (selected.panel) {
            selected.panel.style.display = 'block';
            selected.panel.classList.add('active');
        }
    }
}

// ============================================
// URL INPUT HANDLING
// ============================================

function showUrlInput() {
    if (urlInputContainer) urlInputContainer.style.display = 'block';
    if (textInputContainer) textInputContainer.style.display = 'none';
    updateToggleButton(true);
}

function showTextInput() {
    if (urlInputContainer) urlInputContainer.style.display = 'none';
    if (textInputContainer) textInputContainer.style.display = 'block';
    updateToggleButton(false);
}

function updateToggleButton(isUrlMode) {
    if (!toggleUrlBtn) return;

    if (isUrlMode) {
        toggleUrlBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14,2 14,8 20,8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
            Paste text instead
        `;
    } else {
        toggleUrlBtn.innerHTML = `
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
                <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
            </svg>
            Paste URL instead
        `;
    }
}

// ============================================
// URL FETCH STATUS (Simple - just for loading/error)
// ============================================

function showUrlStatus(type, message) {
    if (!urlFetchStatus) return;

    urlFetchStatus.style.display = 'flex';
    urlFetchStatus.className = `url-fetch-status ${type}`;

    urlFetchStatus.innerHTML = `
        <span class="status-icon">${getStatusIcon(type)}</span>
        <span class="status-text">${message}</span>
    `;
}

function hideUrlStatus() {
    if (urlFetchStatus) {
        urlFetchStatus.style.display = 'none';
    }
}

function getStatusIcon(type) {
    const icons = {
        loading: '⏳',
        success: '✓',
        error: '✕',
        info: 'i'
    };
    return icons[type] || '•';
}

// ============================================
// ARTICLE METADATA DISPLAY (Separate section above text)
// ============================================

/**
 * Show article metadata in the dedicated container above the text area
 * This is called after successfully fetching a URL
 */
function showArticleMetadata(details) {
    const container = document.getElementById('articleMetadataContainer');
    if (!container || !details) return;

    container.style.display = 'block';
    container.innerHTML = buildArticleMetadataPanel(details);
}

/**
 * Hide the article metadata panel
 */
function hideArticleMetadata() {
    const container = document.getElementById('articleMetadataContainer');
    if (container) {
        container.style.display = 'none';
        container.innerHTML = '';
    }
}

/**
 * Build the article metadata panel HTML
 */
function buildArticleMetadataPanel(details) {
    let html = '<div class="article-metadata-panel">';

    // Header with source URL
    html += `
        <div class="metadata-header">
            <span class="metadata-header-label">Source Article</span>
            <button class="metadata-close-btn" onclick="hideArticleMetadata()" title="Close">×</button>
        </div>
    `;

    // Article info section
    html += '<div class="metadata-section article-info">';

    // Title
    if (details.title) {
        html += `
            <div class="metadata-row title-row">
                <span class="metadata-value title-value">${escapeHtml(details.title)}</span>
            </div>
        `;
    }

    // Author and Date
    const authorDateParts = [];
    if (details.author) {
        authorDateParts.push(`<span class="author-value">${escapeHtml(details.author)}</span>`);
    }
    if (details.publication_date || details.publication_date_raw) {
        const dateDisplay = details.publication_date || details.publication_date_raw;
        authorDateParts.push(`<span class="date-value">${escapeHtml(dateDisplay)}</span>`);
    }
    if (authorDateParts.length > 0) {
        html += `
            <div class="metadata-row author-date-row">
                ${authorDateParts.join('<span class="metadata-separator">•</span>')}
            </div>
        `;
    }

    // Publication name, type, section
    const pubParts = [];
    if (details.publication_name) {
        pubParts.push(`<span class="publication-name">${escapeHtml(details.publication_name)}</span>`);
    }
    if (details.article_type) {
        pubParts.push(`<span class="article-type-badge">${escapeHtml(details.article_type)}</span>`);
    }
    if (details.section) {
        pubParts.push(`<span class="section-badge">${escapeHtml(details.section)}</span>`);
    }
    if (pubParts.length > 0) {
        html += `
            <div class="metadata-row publication-row">
                ${pubParts.join(' ')}
            </div>
        `;
    }

    // URL display
    if (details.url) {
        html += `
            <div class="metadata-row url-row">
                <a href="${escapeHtml(details.url)}" target="_blank" rel="noopener" class="source-url-link">
                    ${escapeHtml(details.domain || details.url)}
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                        <polyline points="15 3 21 3 21 9"/>
                        <line x1="10" y1="14" x2="21" y2="3"/>
                    </svg>
                </a>
            </div>
        `;
    }

    html += '</div>'; // End article-info

    // Credibility section
    if (details.credibility) {
        html += buildCredibilitySection(details.credibility);
    }

    // Content stats
    if (details.content_length) {
        html += `
            <div class="metadata-section content-stats">
                <span class="content-length">${formatNumber(details.content_length)} characters extracted</span>
            </div>
        `;
    }

    html += '</div>'; // End article-metadata-panel

    return html;
}

/**
 * Build the credibility section
 */
function buildCredibilitySection(credibility) {
    const tier = credibility.tier || 3;
    const tierColor = getTierColor(tier);
    const tierLabel = getTierLabel(tier);

    let html = `
        <div class="metadata-section credibility-section">
            <div class="credibility-header">
                <span class="credibility-tier-badge" style="background: ${tierColor}">
                    Tier ${tier}
                </span>
                <span class="credibility-tier-label">${tierLabel}</span>
            </div>
    `;

    // Credibility details
    const credDetails = [];

    if (credibility.bias_rating) {
        credDetails.push({
            label: 'Bias',
            value: credibility.bias_rating,
            class: getBiasClass(credibility.bias_rating)
        });
    }

    if (credibility.factual_reporting) {
        credDetails.push({
            label: 'Factual Reporting',
            value: credibility.factual_reporting,
            class: getFactualClass(credibility.factual_reporting)
        });
    }

    if (credibility.rating) {
        credDetails.push({
            label: 'Rating',
            value: credibility.rating,
            class: ''
        });
    }

    if (credDetails.length > 0) {
        html += '<div class="credibility-details">';
        credDetails.forEach(detail => {
            html += `
                <div class="credibility-detail ${detail.class}">
                    <span class="detail-label">${detail.label}</span>
                    <span class="detail-value">${escapeHtml(detail.value)}</span>
                </div>
            `;
        });
        html += '</div>';
    }

    // Propaganda warning
    if (credibility.is_propaganda) {
        html += `
            <div class="credibility-warning propaganda-warning">
                ⚠️ Identified as propaganda source
            </div>
        `;
    }

    // Special tags
    if (credibility.special_tags && credibility.special_tags.length > 0) {
        html += `
            <div class="special-tags">
                ${credibility.special_tags.map(tag => `<span class="special-tag">${escapeHtml(tag)}</span>`).join('')}
            </div>
        `;
    }

    // MBFC link
    if (credibility.mbfc_url) {
        html += `
            <div class="mbfc-link">
                <a href="${escapeHtml(credibility.mbfc_url)}" target="_blank" rel="noopener">
                    View MBFC Report →
                </a>
            </div>
        `;
    }

    html += '</div>';

    return html;
}

// ============================================
// HELPER FUNCTIONS
// ============================================

function getTierColor(tier) {
    const colors = {
        1: '#6B9B6B',
        2: '#8AAF6B',
        3: '#E8B84A',
        4: '#E89B4A',
        5: '#F06449'
    };
    return colors[tier] || '#9A9A9A';
}

function getTierLabel(tier) {
    const labels = {
        1: 'Highly Credible',
        2: 'Credible',
        3: 'Mixed Credibility',
        4: 'Low Credibility',
        5: 'Unreliable'
    };
    return labels[tier] || 'Unknown';
}

function getBiasClass(bias) {
    if (!bias) return '';
    const biasLower = bias.toLowerCase();
    if (biasLower.includes('left')) return 'bias-left';
    if (biasLower.includes('right')) return 'bias-right';
    if (biasLower.includes('center')) return 'bias-center';
    return '';
}

function getFactualClass(factual) {
    if (!factual) return '';
    const factLower = factual.toLowerCase();
    if (factLower.includes('high') || factLower.includes('very high')) return 'factual-high';
    if (factLower.includes('mostly')) return 'factual-mostly';
    if (factLower.includes('mixed')) return 'factual-mixed';
    if (factLower.includes('low')) return 'factual-low';
    return '';
}

function formatNumber(num) {
    if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'k';
    }
    return num.toString();
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function clearUrlInput() {
    if (articleUrl) articleUrl.value = '';
    hideUrlStatus();
    hideArticleMetadata();
    setLastFetchedArticle(null);
}

// ============================================
// BIAS MODEL TABS
// ============================================

function initBiasModelTabs() {
    if (!modelTabs) return;

    modelTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const model = tab.dataset.model;

            modelTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            const gptAnalysis = document.getElementById('gptAnalysis');
            const claudeAnalysis = document.getElementById('claudeAnalysis');
            const consensusAnalysis = document.getElementById('consensusAnalysis');

            if (gptAnalysis) gptAnalysis.style.display = model === 'gpt' ? 'block' : 'none';
            if (claudeAnalysis) claudeAnalysis.style.display = model === 'claude' ? 'block' : 'none';
            if (consensusAnalysis) consensusAnalysis.style.display = model === 'consensus' ? 'block' : 'none';
        });
    });
}

// ============================================
// MANIPULATION INNER TABS
// ============================================

function initManipulationTabs() {
    const manipInnerTabs = document.querySelectorAll('.manip-inner-tab');

    manipInnerTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.manipTab;

            manipInnerTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            const summaryTab = document.getElementById('manipSummaryTab');
            const factsTab = document.getElementById('manipFactsTab');

            if (summaryTab) summaryTab.style.display = tabName === 'summary' ? 'block' : 'none';
            if (factsTab) factsTab.style.display = tabName === 'facts' ? 'block' : 'none';
        });
    });
}