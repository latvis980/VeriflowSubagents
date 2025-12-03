// static/js/modal.js - Modal Handling

// ============================================
// MODAL FUNCTIONS
// ============================================

function showPlainTextModal() {
    plainTextModal.style.display = 'flex';
}

function hidePlainTextModal() {
    plainTextModal.style.display = 'none';
}

// ============================================
// MODAL EVENT LISTENERS SETUP
// ============================================

function initModalListeners() {
    switchToTextMode.addEventListener('click', () => {
        hidePlainTextModal();
        switchMode('text-factcheck');
        if (AppState.pendingContent) {
            processContent(AppState.pendingContent, 'text');
            AppState.pendingContent = null;
        }
    });

    // Key Claims mode from modal
    if (switchToKeyClaimsMode) {
        switchToKeyClaimsMode.addEventListener('click', () => {
            hidePlainTextModal();
            switchMode('key-claims');
            if (AppState.pendingContent) {
                processContent(AppState.pendingContent, 'key-claims');
                AppState.pendingContent = null;
            }
        });
    }

    switchToBiasMode.addEventListener('click', () => {
        hidePlainTextModal();
        switchMode('bias-analysis');
        if (AppState.pendingContent) {
            processContent(AppState.pendingContent, 'bias');
            AppState.pendingContent = null;
        }
    });

    switchToLieMode.addEventListener('click', () => {
        hidePlainTextModal();
        switchMode('lie-detection');
        if (AppState.pendingContent) {
            processContent(AppState.pendingContent, 'lie-detection');
            AppState.pendingContent = null;
        }
    });

    continueAnyway.addEventListener('click', () => {
        hidePlainTextModal();
        if (AppState.pendingContent) {
            processContent(AppState.pendingContent, 'html');
            AppState.pendingContent = null;
        }
    });

    closeModal.addEventListener('click', () => {
        hidePlainTextModal();
        AppState.pendingContent = null;
    });

    plainTextModal.addEventListener('click', (e) => {
        if (e.target === plainTextModal) {
            hidePlainTextModal();
            AppState.pendingContent = null;
        }
    });
}
