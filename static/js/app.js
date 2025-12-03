// static/js/app.js - Main Application Entry Point
// This file ties together all modules and sets up event listeners

// ============================================
// ANALYZE BUTTON HANDLER
// ============================================

async function handleAnalyze() {
    const content = htmlInput.value.trim();

    if (!content) {
        showError('Please paste some content to analyze.');
        return;
    }

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
// DISPLAY RESULTS ROUTER
// ============================================

function displayCombinedResults(type) {
    hideAllSections();
    showSection(resultsSection);

    // Hide ALL tabs first
    factCheckTab.style.display = 'none';
    if (keyClaimsTab) keyClaimsTab.style.display = 'none';
    biasAnalysisTab.style.display = 'none';
    lieDetectionTab.style.display = 'none';

    // Show ONLY the tab for what was just run
    switch (type) {
        case 'html':
            // LLM Output verification
            factCheckTab.style.display = 'block';
            displayVerificationResults();
            switchResultTab('fact-check');
            break;

        case 'text':
            // Web Search fact-check
            factCheckTab.style.display = 'block';
            displayVerificationResults();
            switchResultTab('fact-check');
            break;

        case 'key-claims':
            // Key Claims
            if (keyClaimsTab) keyClaimsTab.style.display = 'block';
            displayKeyClaimsResults();
            switchResultTab('key-claims');
            break;

        case 'bias':
            // Bias Analysis
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
        publicationUrl.value = '';  // NEW
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
        publicationUrl.value = '';  // NEW: was publicationName
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
    initModalListeners();
    initBiasModelTabs();
    
    console.log('✅ VeriFlow app initialized successfully');
    console.log('📦 Modules loaded: config, utils, ui, modal, api, renderers');
}

// Run initialization when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
