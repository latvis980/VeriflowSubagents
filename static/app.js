// static/app.js - Enhanced with proper pipeline separation + Key Claims mode

// ============================================
// DOM ELEMENTS
// ============================================

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
const keyClaimsInstructions = document.getElementById('keyClaimsInstructions');
const biasAnalysisInstructions = document.getElementById('biasAnalysisInstructions');
const lieDetectionInstructions = document.getElementById('lieDetectionInstructions');
const inputSectionTitle = document.getElementById('inputSectionTitle');
const inputHelpText = document.getElementById('inputHelpText');
const contentFormatIndicator = document.getElementById('contentFormatIndicator');

// Modal elements
const plainTextModal = document.getElementById('plainTextModal');
const switchToTextMode = document.getElementById('switchToTextMode');
const switchToKeyClaimsMode = document.getElementById('switchToKeyClaimsMode');
const switchToBiasMode = document.getElementById('switchToBiasMode');
const switchToLieMode = document.getElementById('switchToLieMode');
const continueAnyway = document.getElementById('continueAnyway');
const closeModal = document.getElementById('closeModal');

// Tab elements
const factCheckTab = document.getElementById('factCheckTab');
const keyClaimsTab = document.getElementById('keyClaimsTab');
const biasAnalysisTab = document.getElementById('biasAnalysisTab');
const lieDetectionTab = document.getElementById('lieDetectionTab');
const factCheckResults = document.getElementById('factCheckResults');
const keyClaimsResults = document.getElementById('keyClaimsResults');
const biasAnalysisResults = document.getElementById('biasAnalysisResults');
const lieDetectionResults = document.getElementById('lieDetectionResults');

// Model tabs for bias analysis
const modelTabs = document.querySelectorAll('.model-tab');

const factsList = document.getElementById('factsList');
const keyClaimsList = document.getElementById('keyClaimsList');
const exportBtn = document.getElementById('exportBtn');
const newCheckBtn = document.getElementById('newCheckBtn');
const retryBtn = document.getElementById('retryBtn');


// ============================================
// STATE
// ============================================

let currentMode = 'llm-output'; // 'llm-output', 'text-factcheck', 'key-claims', 'bias-analysis', 'lie-detection'
let currentLLMVerificationResults = null;
let currentFactCheckResults = null;
let currentKeyClaimsResults = null;  // NEW: Key Claims results
let currentBiasResults = null;
let currentLieDetectionResults = null;
let activeEventSources = [];
let currentJobIds = {
    llmVerification: null,
    factCheck: null,
    keyClaims: null,  // NEW
    biasCheck: null,
    lieDetection: null
};
let pendingContent = null;

// ============================================
// MODE SELECTION
// ============================================

function switchMode(mode) {
    currentMode = mode;

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

// Mode tab click listeners
modeTabs.forEach(tab => {
    tab.addEventListener('click', () => {
        switchMode(tab.dataset.mode);
    });
});

// ============================================
// INPUT VALIDATION
// ============================================

htmlInput.addEventListener('input', () => {
    const content = htmlInput.value.trim();

    if (!content) {
        hideContentFormatIndicator();
        return;
    }

    // Only show format indicator for LLM output mode
    if (currentMode === 'llm-output') {
        const hasLinks = hasHTMLLinks(content);
        const linkCount = countLinks(content);
        showContentFormatIndicator(hasLinks, linkCount);
    } else {
        hideContentFormatIndicator();
    }
});

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
// MODAL HANDLING
// ============================================

function showPlainTextModal() {
    plainTextModal.style.display = 'flex';
}

function hidePlainTextModal() {
    plainTextModal.style.display = 'none';
}

switchToTextMode.addEventListener('click', () => {
    hidePlainTextModal();
    switchMode('text-factcheck');
    if (pendingContent) {
        processContent(pendingContent, 'text');
        pendingContent = null;
    }
});

// NEW: Key Claims mode from modal
if (switchToKeyClaimsMode) {
    switchToKeyClaimsMode.addEventListener('click', () => {
        hidePlainTextModal();
        switchMode('key-claims');
        if (pendingContent) {
            processContent(pendingContent, 'key-claims');
            pendingContent = null;
        }
    });
}

switchToBiasMode.addEventListener('click', () => {
    hidePlainTextModal();
    switchMode('bias-analysis');
    if (pendingContent) {
        processContent(pendingContent, 'bias');
        pendingContent = null;
    }
});

switchToLieMode.addEventListener('click', () => {
    hidePlainTextModal();
    switchMode('lie-detection');
    if (pendingContent) {
        processContent(pendingContent, 'lie-detection');
        pendingContent = null;
    }
});

continueAnyway.addEventListener('click', () => {
    hidePlainTextModal();
    if (pendingContent) {
        processContent(pendingContent, 'html');
        pendingContent = null;
    }
});

closeModal.addEventListener('click', () => {
    hidePlainTextModal();
    pendingContent = null;
});

plainTextModal.addEventListener('click', (e) => {
    if (e.target === plainTextModal) {
        hidePlainTextModal();
        pendingContent = null;
    }
});

// ============================================
// ANALYZE BUTTON
// ============================================

checkBtn.addEventListener('click', handleAnalyze);

async function handleAnalyze() {
    const content = htmlInput.value.trim();

    if (!content) {
        showError('Please paste some content to analyze.');
        return;
    }

    // Mode-specific validation
    if (currentMode === 'llm-output') {
        const links = hasHTMLLinks(content);

        if (!links) {
            pendingContent = content;
            showPlainTextModal();
            return;
        }

        processContent(content, 'html');

    } else if (currentMode === 'text-factcheck') {
        processContent(content, 'text');

    } else if (currentMode === 'key-claims') {
        processContent(content, 'key-claims');

    } else if (currentMode === 'bias-analysis') {
        processContent(content, 'bias');

    } else if (currentMode === 'lie-detection') {
        processContent(content, 'lie-detection');
    }
}

// ============================================
// PROCESS CONTENT
// ============================================

async function processContent(content, type) {
    closeAllStreams();

    setLoadingState(true);
    stopBtn.disabled = false;
    hideAllSections();
    showSection(statusSection);
    clearProgressLog();

    // CLEAR ALL RESULTS
    currentLLMVerificationResults = null;
    currentFactCheckResults = null;
    currentKeyClaimsResults = null;
    currentBiasResults = null;
    currentLieDetectionResults = null;
    currentJobIds.llmVerification = null;
    currentJobIds.factCheck = null;
    currentJobIds.keyClaims = null;
    currentJobIds.biasCheck = null;
    currentJobIds.lieDetection = null;

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
            // NEW: Key Claims Pipeline
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
// LLM VERIFICATION
// ============================================

async function runLLMVerification(content) {
    try {
        const response = await fetch('/api/check', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: content,
                input_type: 'html'
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'LLM verification failed');
        }

        const data = await response.json();
        currentJobIds.llmVerification = data.job_id;

        await streamLLMVerificationProgress(data.job_id);

    } catch (error) {
        console.error('LLM verification error:', error);
        addProgress(`❌ LLM verification failed: ${error.message}`, 'error');
        throw error;
    }
}

async function streamLLMVerificationProgress(jobId) {
    const result = await streamJobProgress(jobId, '🔍');
    currentLLMVerificationResults = result;
    console.log('LLM Verification completed:', result);
    addProgress('✅ LLM interpretation verification completed');
    return result;
}

// ============================================
// FACT CHECKING (Web Search Only)
// ============================================

async function runFactCheck(content) {
    try {
        const response = await fetch('/api/check', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: content,
                input_type: 'text'
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Fact check failed');
        }

        const data = await response.json();
        currentJobIds.factCheck = data.job_id;

        await streamFactCheckProgress(data.job_id);

    } catch (error) {
        console.error('Fact check error:', error);
        addProgress(`❌ Fact check failed: ${error.message}`, 'error');
        throw error;
    }
}

async function streamFactCheckProgress(jobId) {
    const result = await streamJobProgress(jobId, '🔎');
    currentFactCheckResults = result;
    console.log('Fact check completed:', result);
    addProgress('✅ Fact checking completed');
    return result;
}

// ============================================
// KEY CLAIMS CHECKING (NEW)
// ============================================

async function runKeyClaimsCheck(content) {
    try {
        const response = await fetch('/api/key-claims', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: content
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Key claims analysis failed');
        }

        const data = await response.json();
        currentJobIds.keyClaims = data.job_id;

        await streamKeyClaimsProgress(data.job_id);

    } catch (error) {
        console.error('Key claims error:', error);
        addProgress(`❌ Key claims analysis failed: ${error.message}`, 'error');
        throw error;
    }
}

async function streamKeyClaimsProgress(jobId) {
    const result = await streamJobProgress(jobId, '🎯');
    currentKeyClaimsResults = result;
    console.log('Key claims analysis completed:', result);
    addProgress('✅ Key claims analysis completed');
    return result;
}

// ============================================
// UNIFIED STREAMING WITH AUTO-RECONNECTION
// ============================================

function streamJobProgress(jobId, emoji = '⏳', reconnectAttempts = 0) {
    const maxReconnects = 3;
    const baseDelay = 2000;

    return new Promise((resolve, reject) => {
        const eventSource = new EventSource(`/api/job/${jobId}/stream`);
        activeEventSources.push(eventSource);

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.heartbeat) {
                return;
            }

            if (data.status === 'completed') {
                addProgress(`${emoji} Complete!`);
                eventSource.close();
                resolve(data.result);
                return;
            }

            if (data.status === 'failed') {
                addProgress(`${emoji} Failed: ${data.error || 'Unknown error'}`, 'error');
                eventSource.close();
                reject(new Error(data.error || 'Job failed'));
                return;
            }

            if (data.status === 'cancelled') {
                addProgress(`${emoji} Job cancelled`);
                eventSource.close();
                reject(new Error('Job cancelled by user'));
                return;
            }

            if (data.message) {
                addProgress(data.message);
            }

            if (data.status && !data.message) {
                addProgress(`🔄 ${data.status}`);
            }
        };

        eventSource.onerror = (error) => {
            console.error('EventSource error:', error);
            eventSource.close();

            if (reconnectAttempts < maxReconnects) {
                const delay = baseDelay * Math.pow(2, reconnectAttempts);
                console.log(`Connection lost. Reconnecting in ${delay/1000}s... (Attempt ${reconnectAttempts + 1}/${maxReconnects})`);
                addProgress(`⚠️ Connection lost. Reconnecting in ${delay/1000}s...`);

                setTimeout(() => {
                    console.log(`Reconnecting to job ${jobId}...`);
                    streamJobProgress(jobId, emoji, reconnectAttempts + 1)
                        .then(resolve)
                        .catch(reject);
                }, delay);
            } else {
                addProgress(`❌ Connection failed after ${maxReconnects} attempts`, 'error');
                reject(new Error('Stream connection failed after retries'));
            }
        };
    });
}

// ============================================
// BIAS ANALYSIS
// ============================================

async function runBiasCheck(content) {
    try {
        addProgress('📊 Starting bias analysis...');

        const pubName = publicationName.value.trim() || null;

        const response = await fetch('/api/check-bias', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                text: content,
                publication_name: pubName
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Bias check failed');
        }

        const data = await response.json();
        currentJobIds.biasCheck = data.job_id;

        await streamBiasProgress(data.job_id);

    } catch (error) {
        console.error('Bias check error:', error);
        addProgress(`❌ Bias analysis failed: ${error.message}`, 'error');
        throw error;
    }
}

async function streamBiasProgress(jobId) {
    const result = await streamJobProgress(jobId, '📊');
    currentBiasResults = result;
    addProgress('✅ Bias analysis completed');
    return result;
}

// ============================================
// LIE DETECTION
// ============================================

async function runLieDetection(content) {
    try {
        addProgress('🕵️ Analyzing text for deception markers...');

        const response = await fetch('/api/check-lie-detection', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                text: content
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Lie detection failed');
        }

        const data = await response.json();
        currentJobIds.lieDetection = data.job_id;

        await streamLieDetectionProgress(data.job_id);

    } catch (error) {
        console.error('Lie detection error:', error);
        addProgress(`❌ Lie detection failed: ${error.message}`, 'error');
        throw error;
    }
}

async function streamLieDetectionProgress(jobId) {
    const result = await streamJobProgress(jobId, '🕵️');
    currentLieDetectionResults = result;
    addProgress('✅ Lie detection analysis completed');
    return result;
}

// ============================================
// DISPLAY RESULTS
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
// DISPLAY KEY CLAIMS RESULTS (NEW)
// ============================================

function displayKeyClaimsResults() {
    if (!currentKeyClaimsResults) {
        console.error('No key claims results available');
        return;
    }

    console.log('📦 Displaying Key Claims Results:', currentKeyClaimsResults);

    const data = currentKeyClaimsResults;
    const claims = data.key_claims || [];
    const summary = data.summary || {};

    // Update summary stats
    document.getElementById('kcTotalClaims').textContent = summary.total_key_claims || claims.length || 0;
    document.getElementById('kcVerifiedCount').textContent = summary.verified_count || 0;
    document.getElementById('kcPartialCount').textContent = summary.partial_count || 0;
    document.getElementById('kcUnverifiedCount').textContent = summary.unverified_count || 0;
    
    // Overall credibility
    const credibilityEl = document.getElementById('kcOverallCredibility');
    if (credibilityEl) {
        credibilityEl.textContent = summary.overall_credibility || '-';
    }

    // Session info
    document.getElementById('kcSessionId').textContent = data.session_id || '-';
    document.getElementById('kcProcessingTime').textContent = Math.round(data.processing_time || 0) + 's';

    // R2 link - with null checks
    const r2Link = document.getElementById('kcR2Link');
    const r2Sep = document.getElementById('kcR2Sep');
    if (r2Link && r2Sep) {
        if (data.r2_upload && data.r2_upload.success && data.r2_upload.url) {
            r2Link.href = data.r2_upload.url;
            r2Link.style.display = 'inline';
            r2Sep.style.display = 'inline';
        } else {
            r2Link.style.display = 'none';
            r2Sep.style.display = 'none';
        }
    }

    // Render key claims list
    keyClaimsList.innerHTML = '';
    claims.forEach((claim, index) => {
        keyClaimsList.appendChild(createKeyClaimCard(claim, index + 1));
    });
}

function createKeyClaimCard(claim, number) {
    const card = document.createElement('div');
    card.className = 'fact-card key-claim-card';

    const score = claim.match_score || 0;

    // NEW: Add 'debunked' class for scores <= 0.1
    let scoreClass;
    if (score <= 0.1) {
        scoreClass = 'debunked';
    } else if (score >= 0.9) {
        scoreClass = 'accurate';
    } else if (score >= 0.7) {
        scoreClass = 'good';
    } else {
        scoreClass = 'questionable';
    }

    const statementText = claim.statement || 'No statement available';

    // NEW: Use 'report' field with fallback to old fields for backwards compatibility
    const reportText = claim.report || claim.assessment || 'No report available';

    // NEW: Check if this is a debunked/hoax claim (score <= 0.1)
    const isDebunked = score <= 0.1 && score > 0;
    const debunkedBadge = isDebunked ? '<span class="debunked-badge">🚫 DEBUNKED</span>' : '';

    card.innerHTML = `
        <div class="fact-header ${scoreClass}">
            <div class="fact-title-row">
                <span class="fact-number">#${number}</span>
                <span class="claim-badge">KEY CLAIM</span>
                ${debunkedBadge}
            </div>
            <span class="fact-score ${scoreClass}">${Math.round(score * 100)}%</span>
        </div>
        <div class="fact-statement">${escapeHtml(statementText)}</div>
        <div class="fact-report">${escapeHtml(reportText)}</div>
    `;

    return card;
}

// ============================================
// DISPLAY VERIFICATION RESULTS (Unified)
// ============================================

function displayVerificationResults() {
    let data, facts, sessionId, duration, pipelineType, auditUrl;

    if (currentLLMVerificationResults) {
        console.log('📦 Displaying LLM Verification Results');

        if (currentLLMVerificationResults.factCheck) {
            data = currentLLMVerificationResults.factCheck;
        } else {
            data = currentLLMVerificationResults;
        }

        facts = data.results || data.claims || [];
        sessionId = data.session_id || '-';
        duration = data.duration || data.processing_time || 0;
        pipelineType = 'LLM Interpretation Verification';
        auditUrl = data.audit_url || currentLLMVerificationResults.audit_url;

    } else if (currentFactCheckResults) {
        console.log('📦 Displaying Web Search Fact-Check Results');

        data = currentFactCheckResults;
        facts = data.facts || data.claims || [];
        sessionId = data.session_id || '-';
        duration = data.processing_time || data.duration || 0;
        pipelineType = 'Web Search Fact-Checking';
        auditUrl = data.audit_url;

    } else {
        console.error('No verification results available');
        return;
    }

    console.log(`📊 Processing ${facts.length} facts from ${pipelineType}`);

    if (data.success === false) {
        console.error('Verification marked as failed');
        showError('Verification failed. Please try again.');
        return;
    }

    const totalFacts = facts.length;

    const accurateFacts = facts.filter(f => 
        (f.verification_score || f.match_score || 0) >= 0.9
    ).length;

    const goodFacts = facts.filter(f => {
        const score = f.verification_score || f.match_score || 0;
        return score >= 0.7 && score < 0.9;
    }).length;

    const questionableFacts = facts.filter(f => 
        (f.verification_score || f.match_score || 0) < 0.7
    ).length;

    const avgScore = totalFacts > 0 
        ? (facts.reduce((sum, f) => 
            sum + (f.verification_score || f.match_score || 0), 0
          ) / totalFacts * 100).toFixed(0)
        : 0;

    document.getElementById('totalFacts').textContent = totalFacts;
    document.getElementById('verifiedCount').textContent = accurateFacts;
    document.getElementById('partialCount').textContent = goodFacts;
    document.getElementById('unverifiedCount').textContent = questionableFacts;

    document.getElementById('sessionId').textContent = sessionId;
    document.getElementById('processingTime').textContent = Math.round(duration) + 's';

    const r2Link = document.getElementById('r2Link');
    const r2Sep = document.getElementById('r2Sep');
    if (auditUrl && r2Link) {
        r2Link.href = auditUrl;
        r2Link.style.display = 'inline';
        if (r2Sep) r2Sep.style.display = 'inline';
    } else {
        if (r2Link) r2Link.style.display = 'none';
        if (r2Sep) r2Sep.style.display = 'none';
    }

    factsList.innerHTML = '';
    facts.forEach((fact, index) => {
        factsList.appendChild(createFactCard(fact, index + 1));
    });
}

// ============================================
// CREATE FACT CARD
// ============================================

function createFactCard(fact, number) {
    const card = document.createElement('div');
    card.className = 'fact-card';

    const score = fact.verification_score || fact.match_score || 0;

    // NEW: Add 'debunked' class for scores <= 0.1
    let scoreClass;
    if (score <= 0.1) {
        scoreClass = 'debunked';
    } else if (score >= 0.9) {
        scoreClass = 'accurate';
    } else if (score >= 0.7) {
        scoreClass = 'good';
    } else {
        scoreClass = 'questionable';
    }

    const statementText = fact.claim_text || fact.statement || 'No statement available';

    // NEW: Use 'report' field with fallback to old fields for backwards compatibility
    const reportText = fact.report || fact.assessment || 'No report available';

    // Handle LLM verification specific fields (interpretation_issues)
    let issuesHtml = '';
    if (fact.interpretation_issues && fact.interpretation_issues.length > 0) {
        issuesHtml = `
            <div class="fact-discrepancies">
                <strong>⚠️ Interpretation Issues:</strong>
                <ul>
                    ${fact.interpretation_issues.map(issue => `<li>${escapeHtml(issue)}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    // Sources HTML (unchanged - supports both LLM verification and web search)
    let sourcesHtml = '';
    if (fact.cited_source_urls && fact.cited_source_urls.length > 0) {
        if (fact.cited_source_urls.length === 1) {
            sourcesHtml = `
                <div class="fact-sources">
                    <strong>📎 Source Cited:</strong> 
                    <a href="${escapeHtml(fact.cited_source_urls[0])}" target="_blank" class="source-tag">
                        ${new URL(fact.cited_source_urls[0]).hostname}
                    </a>
                </div>
            `;
        } else {
            const sourceLinks = fact.cited_source_urls.map(url => 
                `<a href="${escapeHtml(url)}" target="_blank" class="source-tag">
                    ${new URL(url).hostname}
                </a>`
            ).join(' ');

            sourcesHtml = `
                <div class="fact-sources">
                    <strong>📎 Sources Cited (${fact.cited_source_urls.length}):</strong> 
                    ${sourceLinks}
                </div>
            `;
        }
    } else if (fact.sources_used && fact.sources_used.length > 0) {
        sourcesHtml = `
            <div class="fact-sources">
                <strong>🔍 Sources Found:</strong> 
                ${fact.sources_used.map(url => 
                    `<a href="${escapeHtml(url)}" target="_blank" class="source-tag">
                        ${new URL(url).hostname}
                    </a>`
                ).join(' ')}
            </div>
        `;
    }

    // NEW: Check if this is a debunked/hoax claim (score <= 0.1)
    const isDebunked = score <= 0.1 && score > 0;
    const debunkedBadge = isDebunked ? '<span class="debunked-badge">🚫 DEBUNKED</span>' : '';

    card.innerHTML = `
        <div class="fact-header ${scoreClass}">
            <span class="fact-number">#${number}</span>
            ${debunkedBadge}
            <span class="fact-score ${scoreClass}">${Math.round(score * 100)}%</span>
        </div>
        <div class="fact-statement">${escapeHtml(statementText)}</div>
        <div class="fact-report">${escapeHtml(reportText)}</div>
        ${issuesHtml}
        ${sourcesHtml}
    `;

    return card;
}

// ============================================
// DISPLAY BIAS RESULTS
// ============================================

function displayBiasResults() {
    if (!currentBiasResults || !currentBiasResults.success) {
        return;
    }

    const analysis = currentBiasResults.analysis;

    const score = analysis.consensus_bias_score || 0;
    const direction = analysis.consensus_direction || 'Unknown';
    const confidence = analysis.confidence || 0;

    document.getElementById('consensusBiasScore').textContent = score.toFixed(1) + '/10';
    document.getElementById('consensusBiasDirection').textContent = direction;
    document.getElementById('biasConfidence').textContent = Math.round(confidence * 100) + '%';

    document.getElementById('biasSessionId').textContent = currentBiasResults.session_id || '-';
    document.getElementById('biasProcessingTime').textContent = Math.round(currentBiasResults.processing_time || 0) + 's';

    displayModelAnalysis('gpt', analysis.gpt_analysis);
    displayModelAnalysis('claude', analysis.claude_analysis);
    displayConsensusAnalysis(analysis);
}

function displayModelAnalysis(model, data) {
    if (!data) return;

    const prefix = model === 'gpt' ? 'gpt' : 'claude';

    document.getElementById(`${prefix}OverallAssessment`).textContent = data.reasoning || '-';

    const indicatorsList = document.getElementById(`${prefix}BiasIndicators`);
    indicatorsList.innerHTML = '';

    if (data.biases_detected && data.biases_detected.length > 0) {
        data.biases_detected.forEach(bias => {
            const li = document.createElement('li');
            li.innerHTML = `<strong>${bias.type}</strong> (${bias.severity}/10): ${bias.evidence}`;
            indicatorsList.appendChild(li);
        });
    } else {
        indicatorsList.innerHTML = '<li>No significant bias indicators detected</li>';
    }

    const languageText = data.balanced_aspects ? data.balanced_aspects.join(' • ') : 'Analysis complete';
    document.getElementById(`${prefix}LanguageAnalysis`).textContent = languageText;
}

function displayConsensusAnalysis(analysis) {
    const agreementList = document.getElementById('areasOfAgreement');
    agreementList.innerHTML = '';
    (analysis.areas_of_agreement || []).forEach(item => {
        const li = document.createElement('li');
        li.textContent = item;
        agreementList.appendChild(li);
    });

    const disagreementList = document.getElementById('areasOfDisagreement');
    disagreementList.innerHTML = '';
    (analysis.areas_of_disagreement || []).forEach(item => {
        const li = document.createElement('li');
        li.textContent = item;
        disagreementList.appendChild(li);
    });

    document.getElementById('finalAssessment').textContent = analysis.final_assessment || '-';

    const recommendationsList = document.getElementById('recommendations');
    recommendationsList.innerHTML = '';
    (analysis.recommendations || []).forEach(rec => {
        const li = document.createElement('li');
        li.textContent = rec;
        recommendationsList.appendChild(li);
    });
}

// ============================================
// DISPLAY LIE DETECTION RESULTS
// ============================================

function displayLieDetectionResults() {
    if (!currentLieDetectionResults || !currentLieDetectionResults.success) {
        return;
    }

    const analysis = currentLieDetectionResults.analysis;

    const riskElement = document.getElementById('lieRiskLevel');
    riskElement.textContent = analysis.risk_level;
    riskElement.className = `risk-value risk-${analysis.risk_level.toLowerCase()}`;

    const scoreElement = document.getElementById('lieCredibilityScore');
    scoreElement.textContent = `${analysis.credibility_score}/100`;
    const credClass = analysis.credibility_score >= 80 ? 'high' : analysis.credibility_score >= 60 ? 'medium' : 'low';
    scoreElement.className = `credibility-value credibility-${credClass}`;

    document.getElementById('lieOverallAssessment').textContent = analysis.overall_assessment;

    const markersContainer = document.getElementById('lieMarkersContainer');
    markersContainer.innerHTML = '';

    if (analysis.markers_detected && analysis.markers_detected.length > 0) {
        analysis.markers_detected.forEach(marker => {
            const markerCard = createMarkerCard(marker);
            markersContainer.appendChild(markerCard);
        });
    } else {
        markersContainer.innerHTML = '<p class="no-markers">✅ No significant deception markers detected.</p>';
    }

    const positiveContainer = document.getElementById('liePositiveIndicators');
    positiveContainer.innerHTML = '';

    if (analysis.positive_indicators && analysis.positive_indicators.length > 0) {
        const list = document.createElement('ul');
        list.className = 'positive-list';
        analysis.positive_indicators.forEach(indicator => {
            const li = document.createElement('li');
            li.textContent = indicator;
            list.appendChild(li);
        });
        positiveContainer.appendChild(list);
    } else {
        positiveContainer.innerHTML = '<p>No positive indicators documented.</p>';
    }

    document.getElementById('lieConclusion').textContent = analysis.conclusion;
    document.getElementById('lieDetailedReasoning').textContent = analysis.reasoning;

    document.getElementById('lieSessionId').textContent = currentLieDetectionResults.session_id || '-';
    document.getElementById('lieProcessingTime').textContent = Math.round(currentLieDetectionResults.processing_time || 0) + 's';

    if (currentLieDetectionResults.r2_url) {
        const link = document.getElementById('lieR2Link');
        link.href = currentLieDetectionResults.r2_url;
        link.style.display = 'inline';
        document.getElementById('lieR2Sep').style.display = 'inline';
    } else {
        document.getElementById('lieR2Link').style.display = 'none';
        document.getElementById('lieR2Sep').style.display = 'none';
    }
}

function createMarkerCard(marker) {
    const card = document.createElement('div');
    card.className = `marker-card severity-${marker.severity.toLowerCase()}`;

    const examplesList = marker.examples.map(ex => `<li>${escapeHtml(ex)}</li>`).join('');

    card.innerHTML = `
        <div class="marker-header">
            <h4>${escapeHtml(marker.category)}</h4>
            <span class="severity-badge">${marker.severity}</span>
        </div>
        <div class="marker-explanation">${escapeHtml(marker.explanation)}</div>
        <div class="marker-examples">
            <strong>Examples from text:</strong>
            <ul>${examplesList}</ul>
        </div>
    `;

    return card;
}

// ============================================
// RESULT TABS
// ============================================

function switchResultTab(tab) {
    // Fix: Use correct class selector 'results-tab'
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

// ============================================
// MODEL TAB SWITCHING FOR BIAS ANALYSIS
// ============================================

// Model tab listeners for bias analysis
modelTabs.forEach(tab => {
    tab.addEventListener('click', () => {
        // Update active tab styling
        modelTabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');

        // Get selected model
        const model = tab.dataset.model;

        // Show/hide the correct analysis panel using display property
        const gptAnalysis = document.getElementById('gptAnalysis');
        const claudeAnalysis = document.getElementById('claudeAnalysis');
        const consensusAnalysis = document.getElementById('consensusAnalysis');

        if (gptAnalysis) {
            gptAnalysis.style.display = model === 'gpt' ? 'block' : 'none';
        }
        if (claudeAnalysis) {
            claudeAnalysis.style.display = model === 'claude' ? 'block' : 'none';
        }
        if (consensusAnalysis) {
            consensusAnalysis.style.display = model === 'consensus' ? 'block' : 'none';
        }
    });
});

// ============================================
// UTILITY FUNCTIONS
// ============================================

function setLoadingState(isLoading) {
    checkBtn.disabled = isLoading;
    clearBtn.disabled = isLoading;
    htmlInput.disabled = isLoading;
    stopBtn.style.display = isLoading ? 'inline-flex' : 'none';
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

function addProgress(message, type = 'info') {
    const entry = document.createElement('div');
    entry.className = `progress-entry ${type}`;
    entry.textContent = message;
    progressLog.appendChild(entry);
    progressLog.scrollTop = progressLog.scrollHeight;
}

function showError(message) {
    hideAllSections();
    showSection(errorSection);
    document.getElementById('errorMessage').textContent = message;
}

function closeAllStreams() {
    activeEventSources.forEach(source => {
        try {
            source.close();
        } catch (e) {
            console.error('Error closing stream:', e);
        }
    });
    activeEventSources = [];
}

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
// BUTTON HANDLERS
// ============================================

clearBtn.addEventListener('click', () => {
    htmlInput.value = '';
    publicationName.value = '';
    hideContentFormatIndicator();
    hideAllSections();
    currentLLMVerificationResults = null;
    currentFactCheckResults = null;
    currentKeyClaimsResults = null;
    currentBiasResults = null;
    currentLieDetectionResults = null;
});

stopBtn.addEventListener('click', () => {
    closeAllStreams();
    addProgress('⏹️ Analysis stopped by user', 'warning');
    setLoadingState(false);
    stopBtn.disabled = true;
});

newCheckBtn.addEventListener('click', () => {
    hideAllSections();
    htmlInput.value = '';
    publicationName.value = '';
    hideContentFormatIndicator();
    currentLLMVerificationResults = null;
    currentFactCheckResults = null;
    currentKeyClaimsResults = null;
    currentBiasResults = null;
    currentLieDetectionResults = null;
});

retryBtn.addEventListener('click', () => {
    hideAllSections();
    if (htmlInput.value.trim()) {
        handleAnalyze();
    }
});

exportBtn.addEventListener('click', () => {
    const data = {
        llmVerification: currentLLMVerificationResults,
        factCheck: currentFactCheckResults,
        keyClaims: currentKeyClaimsResults,
        biasAnalysis: currentBiasResults,
        lieDetection: currentLieDetectionResults,
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
});

// ============================================
// INITIALIZATION
// ============================================

console.log('App initialized successfully with pipeline separation + Key Claims mode');
