// static/js/modal.js - Modal Handling
// VeriFlow Redesign - Minimalist Theme

// ============================================
// MODAL VISIBILITY
// ============================================

function showPlainTextModal() {
    if (plainTextModal) {
        plainTextModal.style.display = 'flex';
    }
}

function hidePlainTextModal() {
    if (plainTextModal) {
        plainTextModal.style.display = 'none';
    }
}

// ============================================
// MODAL LISTENERS
// ============================================

function initModalListeners() {
    // Close button
    if (closeModal) {
        closeModal.addEventListener('click', () => {
            hidePlainTextModal();
            AppState.pendingContent = null;
        });
    }

    // Click outside to close
    if (plainTextModal) {
        plainTextModal.addEventListener('click', (e) => {
            if (e.target === plainTextModal) {
                hidePlainTextModal();
                AppState.pendingContent = null;
            }
        });
    }

    // Escape key to close
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && plainTextModal && plainTextModal.style.display === 'flex') {
            hidePlainTextModal();
            AppState.pendingContent = null;
        }
    });

    // Switch to Key Claims mode
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

    // Switch to Bias mode
    if (switchToBiasMode) {
        switchToBiasMode.addEventListener('click', () => {
            hidePlainTextModal();
            switchMode('bias-analysis');
            
            if (AppState.pendingContent) {
                processContent(AppState.pendingContent, 'bias');
                AppState.pendingContent = null;
            }
        });
    }

    // Switch to Lie Detection mode
    if (switchToLieMode) {
        switchToLieMode.addEventListener('click', () => {
            hidePlainTextModal();
            switchMode('lie-detection');
            
            if (AppState.pendingContent) {
                processContent(AppState.pendingContent, 'lie-detection');
                AppState.pendingContent = null;
            }
        });
    }

    // Continue with LLM mode anyway
    if (continueAnyway) {
        continueAnyway.addEventListener('click', () => {
            hidePlainTextModal();
            
            if (AppState.pendingContent) {
                // Force LLM verification even without links
                processContent(AppState.pendingContent, 'html');
                AppState.pendingContent = null;
            }
        });
    }
}
