// static/js/renderers/comprehensive.js
// VeriFlow - Comprehensive Analysis Mode Renderer
// SIMPLIFIED VERSION - Focuses on human-readable synthesis report

// ============================================
// COMPREHENSIVE RESULTS RENDERER
// ============================================

/**
 * Render comprehensive analysis results
 * @param {Object} data - Full comprehensive analysis result
 */
function renderComprehensiveResults(data) {
    console.log('Rendering comprehensive results:', data);

    // Show the comprehensive results panel
    const panel = document.getElementById('comprehensiveResults');
    if (!panel) {
        console.error('Comprehensive results panel not found');
        return;
    }

    // Render each section
    renderContentClassification(data.content_classification);
    renderSourceCredibility(data.source_verification);
    renderModeRouting(data.mode_routing);
    renderModeReports(data.mode_reports);
    renderSynthesisReport(data.synthesis_report);

    // Update session info
    updateComprehensiveSessionInfo(data);
}

// ============================================
// STAGE 1: CONTENT CLASSIFICATION
// ============================================

function renderContentClassification(classification) {
    if (!classification) {
        console.log('No content classification data');
        return;
    }

    // Content Type
    const typeEl = document.getElementById('compContentType');
    if (typeEl) {
        typeEl.textContent = formatContentType(classification.content_type);
    }

    // Topic/Realm
    const topicEl = document.getElementById('compContentTopic');
    if (topicEl) {
        const realm = classification.realm || 'Unknown';
        const subRealm = classification.sub_realm;
        topicEl.textContent = subRealm ? `${capitalizeFirst(realm)} / ${capitalizeFirst(subRealm)}` : capitalizeFirst(realm);
    }

    // Purpose
    const purposeEl = document.getElementById('compContentPurpose');
    if (purposeEl) {
        purposeEl.textContent = capitalizeFirst(classification.purpose || 'Unknown');
    }

    // Has Sources
    const sourcesEl = document.getElementById('compHasSources');
    if (sourcesEl) {
        sourcesEl.textContent = classification.contains_references ? 'Yes' : 'No';
    }
}

function formatContentType(type) {
    if (!type) return 'Unknown';
    return type
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
}

// ============================================
// STAGE 1: SOURCE CREDIBILITY
// ============================================

function renderSourceCredibility(verification) {
    if (!verification) {
        console.log('No source verification data');
        return;
    }

    // Handle error cases
    if (verification.error || verification.status === 'no_url_to_verify') {
        const tierEl = document.getElementById('compSourceTier');
        if (tierEl) tierEl.textContent = 'N/A';
        return;
    }

    // Trust Level / Tier
    const tierEl = document.getElementById('compSourceTier');
    if (tierEl) {
        const tier = verification.credibility_tier || 'Unknown';
        const tierDesc = verification.tier_description || '';
        tierEl.innerHTML = `<strong>Tier ${tier}</strong> - ${tierDesc}`;
    }

    // Publication name
    const pubEl = document.getElementById('compSourcePublication');
    if (pubEl) {
        pubEl.textContent = verification.domain || verification.publication_name || '—';
    }

    // Bias Rating
    const biasEl = document.getElementById('compSourceBias');
    if (biasEl) {
        biasEl.textContent = verification.bias_rating || '—';
    }

    // Accuracy Record
    const accuracyEl = document.getElementById('compSourceAccuracy');
    if (accuracyEl) {
        accuracyEl.textContent = verification.factual_reporting || '—';
    }
}

// ============================================
// MODE ROUTING (WHAT WE CHECKED)
// ============================================

function renderModeRouting(routing) {
    const checksEl = document.getElementById('compChecksPerformed');
    if (!checksEl) return;

    if (!routing || !routing.selected_modes) {
        checksEl.textContent = 'Mode selection pending...';
        return;
    }

    const modeNames = {
        'key_claims_analysis': 'Fact Checking',
        'bias_analysis': 'Bias Detection',
        'manipulation_detection': 'Manipulation Analysis',
        'lie_detection': 'Deception Indicators',
        'llm_output_verification': 'AI Citation Verification'
    };

    const modes = routing.selected_modes.map(m => modeNames[m] || m).join(', ');
    checksEl.textContent = modes || 'No modes selected';
}

// ============================================
// STAGE 2: MODE REPORTS (Collapsible Details)
// ============================================

function renderModeReports(modeReports) {
    const container = document.getElementById('modeReportsContainer');
    if (!container) return;

    if (!modeReports || Object.keys(modeReports).length === 0) {
        container.innerHTML = '<p class="no-reports">No detailed reports available yet.</p>';
        return;
    }

    const modeConfig = {
        'key_claims_analysis': { title: '📊 Fact Check Results', renderer: renderFactCheckSummary },
        'bias_analysis': { title: '⚖️ Bias Analysis', renderer: renderBiasSummary },
        'manipulation_detection': { title: '🔍 Manipulation Detection', renderer: renderManipulationSummary },
        'lie_detection': { title: '🎭 Deception Indicators', renderer: renderLieDetectionSummary },
        'llm_output_verification': { title: '🤖 AI Citation Check', renderer: renderLLMVerificationSummary }
    };

    let html = '';

    for (const [modeKey, report] of Object.entries(modeReports)) {
        const config = modeConfig[modeKey] || { title: modeKey, renderer: renderGenericSummary };

        html += `
            <div class="mode-report-card" data-mode="${modeKey}">
                <div class="mode-report-header" onclick="toggleModeReport('${modeKey}')">
                    <span class="mode-title">${config.title}</span>
                    <span class="mode-toggle">▼</span>
                </div>
                <div class="mode-report-content" id="modeContent_${modeKey}" style="display: none;">
                    ${config.renderer(report)}
                </div>
            </div>
        `;
    }

    container.innerHTML = html;
}

function toggleModeReport(modeKey) {
    const content = document.getElementById(`modeContent_${modeKey}`);
    const card = content?.closest('.mode-report-card');
    const toggle = card?.querySelector('.mode-toggle');

    if (content) {
        const isVisible = content.style.display !== 'none';
        content.style.display = isVisible ? 'none' : 'block';
        if (toggle) toggle.textContent = isVisible ? '▼' : '▲';
    }
}

// Mode-specific renderers
function renderFactCheckSummary(report) {
    if (!report) return '<p>No fact check data</p>';

    const summary = report.summary || {};
    const total = summary.total_key_claims || 0;
    const verified = summary.verified_count || 0;
    const partial = summary.partial_count || 0;
    const unverified = summary.unverified_count || 0;
    const confidence = summary.average_confidence || 0;

    return `
        <div class="report-summary">
            <div class="summary-stats">
                <div class="stat-item">
                    <span class="stat-value">${total}</span>
                    <span class="stat-label">Claims Checked</span>
                </div>
                <div class="stat-item verified">
                    <span class="stat-value">${verified}</span>
                    <span class="stat-label">Verified</span>
                </div>
                <div class="stat-item partial">
                    <span class="stat-value">${partial}</span>
                    <span class="stat-label">Partial</span>
                </div>
                <div class="stat-item unverified">
                    <span class="stat-value">${unverified}</span>
                    <span class="stat-label">Unverified</span>
                </div>
            </div>
            <div class="confidence-bar-container">
                <span class="confidence-label">Confidence: ${Math.round(confidence * 100)}%</span>
                <div class="confidence-bar">
                    <div class="confidence-fill" style="width: ${confidence * 100}%"></div>
                </div>
            </div>
            <p class="overall-assessment">${summary.overall_credibility || 'Assessment pending'}</p>
        </div>
    `;
}

function renderBiasSummary(report) {
    if (!report) return '<p>No bias analysis data</p>';

    const analysis = report.analysis || {};
    const score = analysis.consensus_bias_score ?? 0;
    const direction = analysis.consensus_direction || 'Unknown';
    const assessment = analysis.final_assessment || 'No assessment available';

    // Determine bias color
    const absScore = Math.abs(score);
    let biasClass = 'low';
    if (absScore > 6) biasClass = 'high';
    else if (absScore > 3) biasClass = 'medium';

    return `
        <div class="report-summary">
            <div class="bias-indicator ${biasClass}">
                <span class="bias-score">${score.toFixed(1)}/10</span>
                <span class="bias-direction">${direction}</span>
            </div>
            <p class="bias-assessment">${escapeHtml(assessment)}</p>
        </div>
    `;
}

function renderManipulationSummary(report) {
    if (!report) return '<p>No manipulation data</p>';

    const score = report.manipulation_score ?? 0;
    const assessment = report.overall_assessment || 'Unknown';
    const agenda = report.detected_agenda;

    let scoreClass = 'low';
    if (score > 6) scoreClass = 'high';
    else if (score > 3) scoreClass = 'medium';

    return `
        <div class="report-summary">
            <div class="manipulation-indicator ${scoreClass}">
                <span class="manip-score">${score.toFixed(1)}/10</span>
                <span class="manip-label">Manipulation Score</span>
            </div>
            <p class="manip-assessment">${escapeHtml(assessment)}</p>
            ${agenda ? `<p class="detected-agenda"><strong>Detected Agenda:</strong> ${escapeHtml(agenda)}</p>` : ''}
        </div>
    `;
}

function renderLieDetectionSummary(report) {
    if (!report) return '<p>No lie detection data</p>';

    const score = report.deception_likelihood_score ?? report.overall_score ?? 0;
    const assessment = report.overall_assessment || 'Unknown';

    let scoreClass = 'low';
    if (score > 6) scoreClass = 'high';
    else if (score > 3) scoreClass = 'medium';

    return `
        <div class="report-summary">
            <div class="deception-indicator ${scoreClass}">
                <span class="deception-score">${score}/10</span>
                <span class="deception-label">Deception Likelihood</span>
            </div>
            <p class="deception-assessment">${escapeHtml(assessment)}</p>
        </div>
    `;
}

function renderLLMVerificationSummary(report) {
    if (!report) return '<p>No LLM verification data</p>';

    const total = report.total_claims || 0;
    const verified = report.verified_count || 0;
    const misrep = report.misrepresented_count || 0;
    const notFound = report.not_found_count || 0;

    return `
        <div class="report-summary">
            <div class="summary-stats">
                <div class="stat-item">
                    <span class="stat-value">${total}</span>
                    <span class="stat-label">Citations Checked</span>
                </div>
                <div class="stat-item verified">
                    <span class="stat-value">${verified}</span>
                    <span class="stat-label">Verified</span>
                </div>
                <div class="stat-item unverified">
                    <span class="stat-value">${misrep}</span>
                    <span class="stat-label">Misrepresented</span>
                </div>
                <div class="stat-item">
                    <span class="stat-value">${notFound}</span>
                    <span class="stat-label">Not Found</span>
                </div>
            </div>
        </div>
    `;
}

function renderGenericSummary(report) {
    return `<pre class="report-json">${escapeHtml(JSON.stringify(report, null, 2))}</pre>`;
}

// ============================================
// STAGE 3: SYNTHESIS REPORT (Main Output)
// ============================================

function renderSynthesisReport(synthesis) {
    console.log('Rendering synthesis report:', synthesis);

    if (!synthesis) {
        console.log('No synthesis report yet');
        // Show loading state
        const scoreEl = document.getElementById('compOverallScore');
        if (scoreEl) scoreEl.textContent = '—';
        return;
    }

    // Overall Score (use new field names)
    const scoreEl = document.getElementById('compOverallScore');
    if (scoreEl) {
        const score = synthesis.overall_score ?? synthesis.overall_credibility_score ?? '—';
        scoreEl.textContent = score;

        // Add color class based on score
        scoreEl.className = 'score-value ' + getScoreClass(score);
    }

    // Overall Rating
    const ratingEl = document.getElementById('compOverallRating');
    if (ratingEl) {
        const rating = synthesis.overall_rating ?? synthesis.overall_credibility_rating ?? '—';
        ratingEl.textContent = rating;
        ratingEl.className = 'rating-badge ' + getRatingClass(rating);
    }

    // Confidence
    const confBar = document.getElementById('compConfidenceBar');
    const confValue = document.getElementById('compConfidenceValue');
    if (confBar && confValue) {
        const conf = synthesis.confidence ?? synthesis.confidence_in_assessment ?? 0;
        confBar.style.width = `${conf}%`;
        confValue.textContent = `${Math.round(conf)}%`;
    }

    // THE MAIN OUTPUT: Human-readable summary
    renderSynthesisSummary(synthesis.summary ?? synthesis.narrative_summary);

    // Key Concerns
    renderKeyConcerns(synthesis.key_concerns);

    // Positive Indicators
    renderPositiveIndicators(synthesis.positive_indicators);

    // Recommendations
    renderRecommendations(synthesis.recommendations);

    // Analysis Notes (if any)
    if (synthesis.analysis_notes) {
        renderAnalysisNotes(synthesis.analysis_notes);
    }
}

/**
 * Render the main human-readable summary - THIS IS THE KEY OUTPUT
 */
function renderSynthesisSummary(summary) {
    const container = document.getElementById('synthesisSummaryContainer');
    if (!container) {
        console.error('Synthesis summary container not found');
        return;
    }

    if (!summary) {
        container.innerHTML = '<p class="no-summary">Analysis in progress...</p>';
        return;
    }

    // Convert markdown-style formatting to HTML
    let formattedSummary = escapeHtml(summary);

    // Convert **bold** to <strong>
    formattedSummary = formattedSummary.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Convert line breaks to paragraphs
    const paragraphs = formattedSummary.split('\n\n').filter(p => p.trim());

    if (paragraphs.length > 0) {
        container.innerHTML = paragraphs.map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('');
    } else {
        // Single paragraph
        container.innerHTML = `<p>${formattedSummary.replace(/\n/g, '<br>')}</p>`;
    }
}

function renderKeyConcerns(concerns) {
    const container = document.getElementById('keyConcernsContainer');
    const section = document.getElementById('keyConcernsSection');
    if (!container || !section) return;

    if (!concerns || concerns.length === 0) {
        section.style.display = 'none';
        return;
    }

    section.style.display = 'block';
    container.innerHTML = concerns.map(concern => `
        <li class="concern-item">
            <span class="concern-icon">⚠️</span>
            <span class="concern-text">${escapeHtml(concern)}</span>
        </li>
    `).join('');
}

function renderPositiveIndicators(positives) {
    const container = document.getElementById('positiveIndicatorsContainer');
    const section = document.getElementById('positiveIndicatorsSection');
    if (!container || !section) return;

    if (!positives || positives.length === 0) {
        section.style.display = 'none';
        return;
    }

    section.style.display = 'block';
    container.innerHTML = positives.map(positive => `
        <li class="positive-item">
            <span class="positive-icon">✅</span>
            <span class="positive-text">${escapeHtml(positive)}</span>
        </li>
    `).join('');
}

function renderRecommendations(recommendations) {
    const container = document.getElementById('recommendationsContainer');
    const section = document.getElementById('recommendationsSection');
    if (!container || !section) return;

    if (!recommendations || recommendations.length === 0) {
        section.style.display = 'none';
        return;
    }

    section.style.display = 'block';
    container.innerHTML = recommendations.map(rec => `
        <li class="recommendation-item">
            <span class="rec-icon">💡</span>
            <span class="rec-text">${escapeHtml(rec)}</span>
        </li>
    `).join('');
}

function renderAnalysisNotes(notes) {
    const container = document.getElementById('analysisNotesContainer');
    if (!container) return;

    if (!notes) {
        container.style.display = 'none';
        return;
    }

    container.style.display = 'block';
    container.innerHTML = `
        <div class="analysis-notes">
            <span class="notes-icon">ℹ️</span>
            <span class="notes-text">${escapeHtml(notes)}</span>
        </div>
    `;
}

// ============================================
// SESSION INFO
// ============================================

function updateComprehensiveSessionInfo(data) {
    const sessionIdEl = document.getElementById('compSessionId');
    const analysisTimeEl = document.getElementById('compAnalysisTime');
    const r2Link = document.getElementById('compR2Link');
    const r2Sep = document.getElementById('compR2Sep');

    if (sessionIdEl) {
        sessionIdEl.textContent = data.session_id || '—';
    }

    if (analysisTimeEl) {
        const time = data.processing_time || data.total_processing_time;
        analysisTimeEl.textContent = time ? `${Math.round(time)}s` : '—';
    }

    if (r2Link && r2Sep) {
        if (data.r2_url || data.audit_url) {
            r2Link.href = data.r2_url || data.audit_url;
            r2Link.style.display = 'inline';
            r2Sep.style.display = 'inline';
        } else {
            r2Link.style.display = 'none';
            r2Sep.style.display = 'none';
        }
    }
}

// ============================================
// HELPER FUNCTIONS
// ============================================

function capitalizeFirst(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase().replace(/_/g, ' ');
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getScoreClass(score) {
    if (score >= 80) return 'score-high';
    if (score >= 65) return 'score-good';
    if (score >= 45) return 'score-mixed';
    if (score >= 25) return 'score-low';
    return 'score-unreliable';
}

function getRatingClass(rating) {
    if (!rating) return '';
    const r = rating.toLowerCase();
    if (r.includes('highly')) return 'rating-highly-credible';
    if (r.includes('credible') && !r.includes('low')) return 'rating-credible';
    if (r.includes('mixed')) return 'rating-mixed';
    if (r.includes('low')) return 'rating-low';
    return 'rating-unreliable';
}

// ============================================
// EXPORTS
// ============================================

if (typeof window !== 'undefined') {
    window.renderComprehensiveResults = renderComprehensiveResults;
    window.toggleModeReport = toggleModeReport;
}