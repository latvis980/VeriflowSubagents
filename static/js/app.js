// static/js/app.js - Main Application Entry Point
// VeriFlow Redesign - Minimalist Theme

// ============================================
// ANALYZE HANDLER
// ============================================

async function handleAnalyze() {
    let content = htmlInput ? htmlInput.value.trim() : '';
    const url = articleUrl ? articleUrl.value.trim() : '';

    // If URL is provided but content is empty, fetch from URL first
    if (url && isValidUrl(url) && !content) {
        try {
            showUrlStatus('loading', 'Fetching article...');
            const result = await fetchArticleFromUrl(url);
            content = result.content;
            if (htmlInput) htmlInput.value = content;
            showUrlStatus('success', 'Article fetched successfully', result);
        } catch (error) {
            showUrlStatus('error', 'Failed to fetch: ' + error.message);
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

    // Mode-specific validation and processing
    const mode = AppState.currentMode;

    if (mode === 'llm-output') {
        const links = hasHTMLLinks(content);

        if (!links) {
            AppState.pendingContent = content;
            showPlainTextModal();
            return;
        }

        processContent(content, 'html');

    } else if (mode === 'text-factcheck') {
        processContent(content, 'text');

    } else if (mode === 'key-claims') {
        processContent(content, 'key-claims');

    } else if (mode === 'bias-analysis') {
        processContent(content, 'bias');

    } else if (mode === 'lie-detection') {
        processContent(content, 'lie-detection');

    } else if (mode === 'manipulation') {
        processContent(content, 'manipulation');
    }
}

// ============================================
// PROCESS CONTENT
// ============================================

async function processContent(content, type) {
    AppState.closeAllStreams();

    setLoadingState(true);
    if (stopBtn) stopBtn.disabled = false;
    hideAllSections();
    showSection(statusSection);
    clearProgressLog();

    // Clear all results
    AppState.clearResults();

    try {
        switch (type) {
            case 'html':
                addProgress('Starting LLM interpretation verification...');
                await runLLMVerification(content);
                break;

            case 'text':
                addProgress('Starting web search fact-checking...');
                await runFactCheck(content);
                break;

            case 'key-claims':
                addProgress('Starting key claims analysis...');
                await runKeyClaimsCheck(content);
                break;

            case 'bias':
                addProgress('Starting bias analysis...');
                await runBiasCheck(content);
                break;

            case 'lie-detection':
                addProgress('Starting deception detection...');
                await runLieDetection(content);
                break;

            case 'manipulation':
                addProgress('Starting manipulation analysis...');
                await runManipulationCheck(content);
                break;
        }

        displayCombinedResults(type);

    } catch (error) {
        console.error('Error during analysis:', error);

        if (!error.message.includes('cancelled') && !error.message.includes('stopped')) {
            showError(error.message || 'An unexpected error occurred. Please try again.');
        }
    } finally {
        setLoadingState(false);
        if (stopBtn) stopBtn.disabled = true;
    }
}

// ============================================
// DISPLAY COMBINED RESULTS
// ============================================

function displayCombinedResults(type) {
    hideAllSections();
    showSection(resultsSection);

    // Hide all result tabs first
    if (factCheckTab) factCheckTab.style.display = 'none';
    if (keyClaimsTab) keyClaimsTab.style.display = 'none';
    if (biasAnalysisTab) biasAnalysisTab.style.display = 'none';
    if (lieDetectionTab) lieDetectionTab.style.display = 'none';
    if (manipulationTab) manipulationTab.style.display = 'none';

    switch (type) {
        case 'html':
        case 'text':
            if (factCheckTab) factCheckTab.style.display = 'block';
            displayVerificationResults();
            switchResultTab('fact-check');
            break;

        case 'key-claims':
            if (keyClaimsTab) keyClaimsTab.style.display = 'block';
            displayKeyClaimsResults();
            switchResultTab('key-claims');
            break;

        case 'bias':
            if (biasAnalysisTab) biasAnalysisTab.style.display = 'block';
            displayBiasResults();
            switchResultTab('bias-analysis');
            break;

        case 'lie-detection':
            if (lieDetectionTab) lieDetectionTab.style.display = 'block';
            displayLieDetectionResults();
            switchResultTab('lie-detection');
            break;

        case 'manipulation':
            if (manipulationTab) manipulationTab.style.display = 'block';
            displayManipulationResults();
            switchResultTab('manipulation');
            break;
    }
}

// ============================================
// EXPORT RESULTS
// ============================================

function exportResults() {
    const mode = AppState.currentMode;
    let data = null;
    let filename = 'veriflow-results';

    switch (mode) {
        case 'llm-output':
        case 'text-factcheck':
            data = AppState.currentLLMVerificationResults || AppState.currentFactCheckResults;
            filename = 'veriflow-factcheck';
            break;
        case 'key-claims':
            data = AppState.currentKeyClaimsResults;
            filename = 'veriflow-keyclaims';
            break;
        case 'bias-analysis':
            data = AppState.currentBiasResults;
            filename = 'veriflow-bias';
            break;
        case 'lie-detection':
            data = AppState.currentLieDetectionResults;
            filename = 'veriflow-deception';
            break;
        case 'manipulation':
            data = AppState.currentManipulationResults;
            filename = 'veriflow-manipulation';
            break;
    }

    if (data) {
        const timestamp = new Date().toISOString().slice(0, 10);
        downloadAsJson(data, `${filename}-${timestamp}.json`);
    } else {
        console.warn('No results to export');
    }
}

// ============================================
// EVENT LISTENERS
// ============================================

function initEventListeners() {
    // Mode card selection
    modeCards.forEach(card => {
        card.addEventListener('click', () => {
            if (card.classList.contains('disabled')) return;
            switchMode(card.dataset.mode);
        });
    });

    // Analyze button
    if (checkBtn) {
        checkBtn.addEventListener('click', handleAnalyze);
    }

    // Clear button
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            if (htmlInput) htmlInput.value = '';
            if (publicationUrl) publicationUrl.value = '';
            clearUrlInput();
            hideContentFormatIndicator();
            hideAllSections();
            AppState.clearResults();
        });
    }

    // Stop button
    if (stopBtn) {
        stopBtn.addEventListener('click', () => {
            AppState.closeAllStreams();
            addProgress('Analysis stopped by user', 'warning');
            setLoadingState(false);
            stopBtn.disabled = true;
        });
    }

    // New check button
    if (newCheckBtn) {
        newCheckBtn.addEventListener('click', () => {
            hideAllSections();
            if (htmlInput) htmlInput.value = '';
            if (publicationUrl) publicationUrl.value = '';
            clearUrlInput();
            hideContentFormatIndicator();
            AppState.clearResults();
        });
    }

    // Retry button
    if (retryBtn) {
        retryBtn.addEventListener('click', () => {
            hideAllSections();
            if (htmlInput && htmlInput.value.trim()) {
                handleAnalyze();
            }
        });
    }

    // Export button
    if (exportBtn) {
        exportBtn.addEventListener('click', exportResults);
    }

    // Result tab switching
    const resultTabs = [
        { tab: factCheckTab, name: 'fact-check' },
        { tab: keyClaimsTab, name: 'key-claims' },
        { tab: biasAnalysisTab, name: 'bias-analysis' },
        { tab: lieDetectionTab, name: 'lie-detection' },
        { tab: manipulationTab, name: 'manipulation' }
    ];

    resultTabs.forEach(({ tab, name }) => {
        if (tab) {
            tab.addEventListener('click', () => switchResultTab(name));
        }
    });

    // Content input change detection (for LLM output mode)
    if (htmlInput) {
        htmlInput.addEventListener('input', debounce(() => {
            if (AppState.currentMode === 'llm-output') {
                const content = htmlInput.value;
                if (content.length > 50) {
                    const linkCount = countLinks(content);
                    showContentFormatIndicator(linkCount > 0, linkCount);
                } else {
                    hideContentFormatIndicator();
                }
            }
        }, 500));
    }
}

// ============================================
// URL INPUT LISTENERS
// ============================================

function initUrlInputListeners() {
    // Toggle URL/Text input
    if (toggleUrlBtn) {
        toggleUrlBtn.addEventListener('click', () => {
            const isUrlVisible = urlInputContainer && urlInputContainer.style.display !== 'none';

            if (isUrlVisible) {
                showTextInput();
            } else {
                showUrlInput();
            }
        });
    }

    // Fetch URL button
    if (fetchUrlBtn && articleUrl) {
        fetchUrlBtn.addEventListener('click', async () => {
            const url = articleUrl.value.trim();

            if (!url) {
                showUrlStatus('error', 'Please enter a URL');
                return;
            }

            if (!isValidUrl(url)) {
                showUrlStatus('error', 'Please enter a valid URL');
                return;
            }

            try {
                showUrlStatus('loading', 'Fetching article...');
                const result = await fetchArticleFromUrl(url);

                if (htmlInput) {
                    htmlInput.value = result.content;
                }

                showUrlStatus('success', `Fetched: ${result.title || result.domain}`, result);

                // ADD THIS LINE - Show the metadata panel
                showArticleMetadata(result);

                // Switch to text view to show content
                showTextInput();

            } catch (error) {
                showUrlStatus('error', 'Failed to fetch: ' + error.message);
            }
        });

        // Enter key in URL input
        articleUrl.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                fetchUrlBtn.click();
            }
        });
    }
}

// ============================================
// INITIALIZATION
// ============================================

function init() {
    initEventListeners();
    initUrlInputListeners();
    initModalListeners();
    initBiasModelTabs();
    initManipulationTabs();

    // Set initial mode
    updatePlaceholder(AppState.currentMode);

    console.log('VeriFlow initialized');
    console.log('Modules: config, utils, ui, modal, api, renderers');
}

// Run initialization when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}