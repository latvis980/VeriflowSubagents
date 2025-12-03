// static/js/renderers/keyclaims.js - Key Claims Rendering

// ============================================
// DISPLAY KEY CLAIMS RESULTS
// ============================================

function displayKeyClaimsResults() {
    if (!AppState.currentKeyClaimsResults) {
        console.error('No key claims results available');
        return;
    }

    console.log('📦 Displaying Key Claims Results:', AppState.currentKeyClaimsResults);

    const data = AppState.currentKeyClaimsResults;
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

// ============================================
// CREATE KEY CLAIM CARD
// ============================================

function createKeyClaimCard(claim, number) {
    const card = document.createElement('div');
    card.className = 'fact-card key-claim-card';

    const score = claim.match_score || 0;

    // Add 'debunked' class for scores <= 0.1
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

    // Use 'report' field with fallback to old fields for backwards compatibility
    const reportText = claim.report || claim.assessment || 'No report available';

    // Check if this is a debunked/hoax claim (score <= 0.1)
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
