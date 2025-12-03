// static/js/config.js - DOM Elements and State

// ============================================
// DOM ELEMENTS
// ============================================

const htmlInput = document.getElementById('htmlInput');
const checkBtn = document.getElementById('checkBtn');
const clearBtn = document.getElementById('clearBtn');
const stopBtn = document.getElementById('stopBtn');
const publicationField = document.getElementById('publicationField');
const publicationUrl = document.getElementById('publicationUrl');

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

const AppState = {
    currentMode: 'llm-output', // 'llm-output', 'text-factcheck', 'key-claims', 'bias-analysis', 'lie-detection'
    currentLLMVerificationResults: null,
    currentFactCheckResults: null,
    currentKeyClaimsResults: null,
    currentBiasResults: null,
    currentLieDetectionResults: null,
    activeEventSources: [],
    currentJobIds: {
        llmVerification: null,
        factCheck: null,
        keyClaims: null,
        biasCheck: null,
        lieDetection: null
    },
    pendingContent: null,

    // Helper methods
    clearResults() {
        this.currentLLMVerificationResults = null;
        this.currentFactCheckResults = null;
        this.currentKeyClaimsResults = null;
        this.currentBiasResults = null;
        this.currentLieDetectionResults = null;
        this.currentJobIds.llmVerification = null;
        this.currentJobIds.factCheck = null;
        this.currentJobIds.keyClaims = null;
        this.currentJobIds.biasCheck = null;
        this.currentJobIds.lieDetection = null;
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
