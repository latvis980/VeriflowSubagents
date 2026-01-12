// static/js/config.js - DOM Elements and State
// VeriFlow Redesign - Minimalist Theme

// ============================================
// DOM ELEMENTS
// ============================================

// Main input elements
const htmlInput = document.getElementById('htmlInput');
const checkBtn = document.getElementById('checkBtn');
const clearBtn = document.getElementById('clearBtn');
const stopBtn = document.getElementById('stopBtn');
const publicationField = document.getElementById('publicationField');
const publicationUrl = document.getElementById('publicationUrl');

// URL input elements
const articleUrl = document.getElementById('articleUrl');
const fetchUrlBtn = document.getElementById('fetchUrlBtn');
const urlFetchStatus = document.getElementById('urlFetchStatus');
const toggleUrlBtn = document.getElementById('toggleUrlInput');
const urlInputContainer = document.getElementById('urlInputContainer');
const textInputContainer = document.getElementById('textInputContainer');

// Sections
const statusSection = document.getElementById('statusSection');
const resultsSection = document.getElementById('resultsSection');
const errorSection = document.getElementById('errorSection');
const progressLog = document.getElementById('progressLog');

// Mode selection elements (updated for new design)
const modeCards = document.querySelectorAll('.mode-card');
const contentFormatIndicator = document.getElementById('contentFormatIndicator');

// Modal elements
const plainTextModal = document.getElementById('plainTextModal');
const switchToKeyClaimsMode = document.getElementById('switchToKeyClaimsMode');
const switchToBiasMode = document.getElementById('switchToBiasMode');
const switchToLieMode = document.getElementById('switchToLieMode');
const continueAnyway = document.getElementById('continueAnyway');
const closeModal = document.getElementById('closeModal');

// Results tab elements
const factCheckTab = document.getElementById('factCheckTab');
const keyClaimsTab = document.getElementById('keyClaimsTab');
const biasAnalysisTab = document.getElementById('biasAnalysisTab');
const lieDetectionTab = document.getElementById('lieDetectionTab');
const manipulationTab = document.getElementById('manipulationTab');

// Results panel elements
const factCheckResults = document.getElementById('factCheckResults');
const keyClaimsResults = document.getElementById('keyClaimsResults');
const biasAnalysisResults = document.getElementById('biasAnalysisResults');
const lieDetectionResults = document.getElementById('lieDetectionResults');
const manipulationResults = document.getElementById('manipulationResults');

// Model tabs for bias analysis
const modelTabs = document.querySelectorAll('.model-tab');

// Container elements
const factsContainer = document.getElementById('factsContainer');
const keyClaimsContainer = document.getElementById('keyClaimsContainer');

// Action buttons
const exportBtn = document.getElementById('exportBtn');
const newCheckBtn = document.getElementById('newCheckBtn');
const retryBtn = document.getElementById('retryBtn');

// ============================================
// APPLICATION STATE
// ============================================

const AppState = {
    // Current mode: 'key-claims', 'bias-analysis', 'lie-detection', 'manipulation', 'text-factcheck', 'llm-output'
    currentMode: 'key-claims',
    
    // Results storage
    currentLLMVerificationResults: null,
    currentFactCheckResults: null,
    currentKeyClaimsResults: null,
    currentBiasResults: null,
    currentLieDetectionResults: null,
    currentManipulationResults: null,
    
    // Active streams
    activeEventSources: [],
    
    // Job IDs
    currentJobIds: {
        llmVerification: null,
        factCheck: null,
        keyClaims: null,
        biasCheck: null,
        lieDetection: null,
        manipulation: null
    },
    
    // Pending content for modal flow
    pendingContent: null,
    
    // Last fetched article data
    lastFetchedArticle: null,

    // Helper methods
    clearResults() {
        // Clear JavaScript state
        this.currentLLMVerificationResults = null;
        this.currentFactCheckResults = null;
        this.currentKeyClaimsResults = null;
        this.currentBiasResults = null;
        this.currentLieDetectionResults = null;
        this.currentManipulationResults = null;
        this.currentJobIds = {
            llmVerification: null,
            factCheck: null,
            keyClaims: null,
            biasCheck: null,
            lieDetection: null,
            manipulation: null
        };

        // Clear DOM containers to remove old rendered results
        const containersToClean = [
            'factsContainer',
            'keyClaimsContainer', 
            'biasContent',
            'lieDetectionContent',
            'manipFactsContainer',
            'manipDetailedContent'
        ];

        containersToClean.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = '';
        });

        // Reset summary stats to zero
        const statsToReset = [
            'verifiedCount', 'issuesCount', 'unverifiedCount',
            'kcTotalClaims', 'kcVerifiedCount', 'kcPartialCount', 'kcUnverifiedCount'
        ];

        statsToReset.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.textContent = '0';
        });
    },

    closeAllStreams() {
        this.activeEventSources.forEach(source => {
            try {
                source.close();
            } catch (e) {
                console.error('Error closing stream:', e);
            }
        });
        this.activeEventSources = [];
    }
};

// ============================================
// HELPER GETTERS
// ============================================

function getLastFetchedArticle() {
    return AppState.lastFetchedArticle;
}

function setLastFetchedArticle(data) {
    AppState.lastFetchedArticle = data;
}
