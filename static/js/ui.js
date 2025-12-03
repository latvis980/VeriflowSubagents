// static/js/ui.js - UI State Management

// ============================================
// LOADING STATE
// ============================================

function setLoadingState(isLoading) {
    checkBtn.disabled = isLoading;
    clearBtn.disabled = isLoading;
    htmlInput.disabled = isLoading;
    stopBtn.style.display = isLoading ? 'inline-flex' : 'none';
}

// ============================================
// SECTION VISIBILITY
// ============================================

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

// ============================================
// PROGRESS LOG
// ============================================

function clearProgressLog() {
    progressLog.innerHTML = '';
}

function addProgress(message, type = 'info') {
    const entry = document.createElement('div');
    entry.className = `progress-entry ${type}`;
    entry.textContent = message;
    progressLog.appendChild(entry);
    progressLog.scrollTop = progressLog.scrollHeight;
}

// ============================================
// CONTENT FORMAT INDICATOR
// ============================================

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

function hideContentFormatIndicator() {
    contentFormatIndicator.style.display = 'none';
}

// ============================================
// MODE SWITCHING
// ============================================

function switchMode(mode) {
    AppState.currentMode = mode;

    // Update tab styling
    modeTabs.forEach(tab => {
        tab.classList.toggle('active', tab.dataset.mode === mode);
    });

    // Update instructions visibility
    llmOutputInstructions.style.display = mode === 'llm-output' ? 'block' : 'none';
    textFactcheckInstructions.style.display = mode === 'text-factcheck' ? 'block' : 'none';
    if (keyClaimsInstructions) {
        keyClaimsInstructions.style.display = mode === 'key-claims' ? 'block' : 'none';
    }
    biasAnalysisInstructions.style.display = mode === 'bias-analysis' ? 'block' : 'none';
    lieDetectionInstructions.style.display = mode === 'lie-detection' ? 'block' : 'none';

    // Update input section labels
    if (mode === 'llm-output') {
        inputSectionTitle.textContent = 'Paste LLM Output with Sources';
        inputHelpText.textContent = 'Paste ChatGPT, Perplexity, or any LLM output with source links';
        publicationField.style.display = 'none';
    } else if (mode === 'text-factcheck') {
        inputSectionTitle.textContent = 'Paste Text to Fact-Check';
        inputHelpText.textContent = 'Paste any text - we\'ll search the web to verify all claims';
        publicationField.style.display = 'none';
    } else if (mode === 'key-claims') {
        inputSectionTitle.textContent = 'Paste Text for Key Claims Analysis';
        inputHelpText.textContent = 'Paste any text - we\'ll identify and verify the 2-3 main arguments';
        publicationField.style.display = 'none';
    } else if (mode === 'bias-analysis') {
        inputSectionTitle.textContent = 'Paste Text to Analyze for Bias';
        inputHelpText.textContent = 'Paste news articles, op-eds, or any content to analyze';
        publicationField.style.display = 'block';
    } else if (mode === 'lie-detection') {
        inputSectionTitle.textContent = 'Paste Article or Text to Analyze';
        inputHelpText.textContent = 'Paste any article or text to analyze for deception markers';
        publicationField.style.display = 'none';
    }

    // Clear format indicator when switching modes
    hideContentFormatIndicator();
}

// ============================================
// RESULT TABS
// ============================================

function switchResultTab(tab) {
    // Update tab button styling
    const tabButtons = document.querySelectorAll('.results-tab');
    tabButtons.forEach(btn => {
        const isActive = 
            (tab === 'fact-check' && btn.id === 'factCheckTab') ||
            (tab === 'key-claims' && btn.id === 'keyClaimsTab') ||
            (tab === 'bias-analysis' && btn.id === 'biasAnalysisTab') ||
            (tab === 'lie-detection' && btn.id === 'lieDetectionTab');
        btn.classList.toggle('active', isActive);
    });

    // Show/hide result panels
    if (factCheckResults) {
        factCheckResults.style.display = tab === 'fact-check' ? 'block' : 'none';
    }
    if (keyClaimsResults) {
        keyClaimsResults.style.display = tab === 'key-claims' ? 'block' : 'none';
    }
    if (biasAnalysisResults) {
        biasAnalysisResults.style.display = tab === 'bias-analysis' ? 'block' : 'none';
    }
    if (lieDetectionResults) {
        lieDetectionResults.style.display = tab === 'lie-detection' ? 'block' : 'none';
    }
}
