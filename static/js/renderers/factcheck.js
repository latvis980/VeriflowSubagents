// static/js/renderers/factcheck.js - Fact Check & LLM Verification Rendering

// ============================================
// DISPLAY VERIFICATION RESULTS (Unified)
// ============================================

function displayVerificationResults() {
    let data, facts, sessionId, duration, pipelineType, auditUrl;

    if (AppState.currentLLMVerificationResults) {
        console.log('📦 Displaying LLM Verification Results');

        if (AppState.currentLLMVerificationResults.factCheck) {
            data = AppState.currentLLMVerificationResults.factCheck;
        } else {
            data = AppState.currentLLMVerificationResults;
        }

        facts = data.results || data.claims || [];
        sessionId = data.session_id || '-';
        duration = data.duration || data.processing_time || 0;
        pipelineType = 'LLM Interpretation Verification';
        auditUrl = data.audit_url || AppState.currentLLMVerificationResults.audit_url;

    } else if (AppState.currentFactCheckResults) {
        console.log('📦 Displaying Web Search Fact-Check Results');

        data = AppState.currentFactCheckResults;
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

    const statementText = fact.claim_text || fact.statement || 'No statement available';

    // Use 'report' field with fallback to old fields for backwards compatibility
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

    // Sources HTML (supports both LLM verification and web search)
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

    // Check if this is a debunked/hoax claim (score <= 0.1)
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
