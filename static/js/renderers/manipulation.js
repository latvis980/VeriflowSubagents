// static/js/renderers/manipulation.js - Manipulation Detection Rendering
// VeriFlow Redesign - Minimalist Theme
// FIXED: Correctly maps to backend response structure

// ============================================
// DISPLAY MANIPULATION RESULTS
// ============================================

function displayManipulationResults() {
    if (!AppState.currentManipulationResults || !AppState.currentManipulationResults.success) {
        console.error('No manipulation results available');
        return;
    }

    console.log('Displaying Manipulation Results:', AppState.currentManipulationResults);

    const data = AppState.currentManipulationResults;

    // ============================================
    // SCORE DISPLAY
    // ============================================
    const scoreElement = document.getElementById('manipScore');
    if (scoreElement) {
        const score = data.manipulation_score || 0;
        scoreElement.textContent = score.toFixed(1);
        scoreElement.className = `manipulation-score-value ${getManipulationScoreClass(score)}`;
    }

    // Score label
    const scoreLabelElement = document.getElementById('manipScoreLabel');
    if (scoreLabelElement) {
        scoreLabelElement.textContent = getManipulationLabel(data.manipulation_score || 0);
    }

    // ============================================
    // SCORE JUSTIFICATION - FIX: Read from data.report.justification
    // ============================================
    const justificationElement = document.getElementById('manipScoreJustification');
    if (justificationElement) {
        // Backend sends: data.report.justification
        const justification = data.report?.justification || data.score_justification || '';
        justificationElement.textContent = justification;
    }

    // ============================================
    // SUMMARY CONTENT - FIX: Read narrative_summary from report
    // ============================================
    const summaryElement = document.getElementById('manipSummaryContent');
    if (summaryElement) {
        summaryElement.innerHTML = '';

        // Backend may send narrative_summary in report object or at top level
        const narrativeSummary = data.report?.narrative_summary || data.narrative_summary || '';

        if (narrativeSummary) {
            const summaryP = document.createElement('p');
            summaryP.className = 'narrative-summary';
            summaryP.textContent = narrativeSummary;
            summaryElement.appendChild(summaryP);
        }

        // Add article summary info if available
        if (data.article_summary) {
            const articleDiv = document.createElement('div');
            articleDiv.className = 'article-summary-section';

            let articleHtml = '';

            if (data.article_summary.main_thesis) {
                articleHtml += `<p><strong>Main Thesis:</strong> ${escapeHtml(data.article_summary.main_thesis)}</p>`;
            }
            if (data.article_summary.detected_agenda) {
                articleHtml += `<p><strong>Detected Agenda:</strong> ${escapeHtml(data.article_summary.detected_agenda)}</p>`;
            }
            if (data.article_summary.political_lean) {
                articleHtml += `<p><strong>Political Lean:</strong> ${escapeHtml(data.article_summary.political_lean)}</p>`;
            }

            if (articleHtml) {
                articleDiv.innerHTML = articleHtml;
                summaryElement.appendChild(articleDiv);
            }
        }

        // ============================================
        // TECHNIQUES DETECTED - FIX: Read from data.report.techniques_used
        // ============================================
        const techniques = data.report?.techniques_used || data.techniques_detected || [];

        if (techniques && techniques.length > 0) {
            const techniquesDiv = document.createElement('div');
            techniquesDiv.className = 'manipulation-techniques';
            techniquesDiv.innerHTML = `
                <h4>Manipulation Techniques Detected</h4>
                <ul>
                    ${techniques.map(t => `<li>${escapeHtml(typeof t === 'string' ? t : t.name || t.technique || JSON.stringify(t))}</li>`).join('')}
                </ul>
            `;
            summaryElement.appendChild(techniquesDiv);
        }

        // Add what article got right (fairness section)
        const gotRight = data.report?.what_got_right || [];
        if (gotRight && gotRight.length > 0) {
            const rightDiv = document.createElement('div');
            rightDiv.className = 'manipulation-got-right';
            rightDiv.innerHTML = `
                <h4>✓ What the Article Got Right</h4>
                <ul>
                    ${gotRight.map(item => `<li>${escapeHtml(item)}</li>`).join('')}
                </ul>
            `;
            summaryElement.appendChild(rightDiv);
        }

        // Add misleading elements
        const misleading = data.report?.misleading_elements || [];
        if (misleading && misleading.length > 0) {
            const misleadingDiv = document.createElement('div');
            misleadingDiv.className = 'manipulation-misleading';
            misleadingDiv.innerHTML = `
                <h4>⚠ Key Misleading Elements</h4>
                <ul>
                    ${misleading.map(item => `<li>${escapeHtml(item)}</li>`).join('')}
                </ul>
            `;
            summaryElement.appendChild(misleadingDiv);
        }
    }

    // ============================================
    // RECOMMENDATION - FIX: Read from data.report.recommendation
    // ============================================
    const recommendationElement = document.getElementById('manipRecommendation');
    const recommendation = data.report?.recommendation || data.recommendation || '';

    if (recommendationElement && recommendation) {
        recommendationElement.innerHTML = `
            <div class="recommendation-box">
                <strong>📋 Reader Recommendation:</strong>
                <p>${escapeHtml(recommendation)}</p>
            </div>
        `;
    } else if (recommendationElement) {
        recommendationElement.innerHTML = '';
    }

    // ============================================
    // FACTS TAB - FIX: Read from data.manipulation_findings
    // ============================================
    const factsContainer = document.getElementById('manipFactsContainer');

    // Backend sends: data.manipulation_findings (not data.analyzed_facts)
    const findings = data.manipulation_findings || data.analyzed_facts || [];

    if (factsContainer) {
        factsContainer.innerHTML = '';

        if (findings.length > 0) {
            findings.forEach((finding, index) => {
                factsContainer.appendChild(createManipulationFactCard(finding, index + 1));
            });
        } else {
            factsContainer.innerHTML = '<p class="no-findings">No specific fact manipulations detected.</p>';
        }
    }

    // ============================================
    // DETAILED CONTENT (expandable section)
    // ============================================
    const detailedContent = document.getElementById('manipDetailedContent');
    if (detailedContent) {
        detailedContent.innerHTML = '';

        // Add article summary details
        if (data.article_summary) {
            const summaryDiv = document.createElement('div');
            summaryDiv.className = 'detailed-section';
            summaryDiv.innerHTML = `
                <h4>Article Analysis</h4>
                <table class="detail-table">
                    <tr><td><strong>Main Thesis</strong></td><td>${escapeHtml(data.article_summary.main_thesis || 'N/A')}</td></tr>
                    <tr><td><strong>Political Lean</strong></td><td>${escapeHtml(data.article_summary.political_lean || 'N/A')}</td></tr>
                    <tr><td><strong>Detected Agenda</strong></td><td>${escapeHtml(data.article_summary.detected_agenda || 'N/A')}</td></tr>
                    <tr><td><strong>Opinion/Fact Ratio</strong></td><td>${escapeHtml(data.article_summary.opinion_fact_ratio || 'N/A')}</td></tr>
                    <tr><td><strong>Emotional Tone</strong></td><td>${escapeHtml(data.article_summary.emotional_tone || 'N/A')}</td></tr>
                </table>
            `;
            detailedContent.appendChild(summaryDiv);
        }

        // Add source credibility if available
        if (data.source_credibility) {
            const credDiv = document.createElement('div');
            credDiv.className = 'detailed-section';
            credDiv.innerHTML = `
                <h4>Source Credibility</h4>
                <table class="detail-table">
                    <tr><td><strong>Publication</strong></td><td>${escapeHtml(data.source_credibility.publication_name || 'Unknown')}</td></tr>
                    <tr><td><strong>Credibility Tier</strong></td><td>${escapeHtml(data.source_credibility.tier || data.source_credibility.credibility_tier || 'Unknown')}</td></tr>
                    <tr><td><strong>Bias Rating</strong></td><td>${escapeHtml(data.source_credibility.bias_rating || 'Unknown')}</td></tr>
                </table>
            `;
            detailedContent.appendChild(credDiv);
        }

        // Raw facts data for debugging
        if (data.facts_analyzed && data.facts_analyzed.length > 0) {
            const factsDiv = document.createElement('div');
            factsDiv.className = 'detailed-section';
            factsDiv.innerHTML = `
                <h4>Extracted Facts (${data.facts_analyzed.length})</h4>
                <ul>
                    ${data.facts_analyzed.map(f => `
                        <li>
                            <strong>${escapeHtml(f.id || '')}</strong>: ${escapeHtml(f.statement || '')}
                            ${f.framing ? `<em>(${escapeHtml(f.framing)})</em>` : ''}
                        </li>
                    `).join('')}
                </ul>
            `;
            detailedContent.appendChild(factsDiv);
        }
    }

    // ============================================
    // SESSION INFO
    // ============================================
    const sessionId = document.getElementById('manipSessionId');
    const processingTime = document.getElementById('manipProcessingTime');

    if (sessionId) sessionId.textContent = data.session_id || '-';
    if (processingTime) processingTime.textContent = Math.round(data.processing_time || 0) + 's';

    // R2 link
    const r2Link = document.getElementById('manipR2Link');
    const r2Sep = document.getElementById('manipR2Sep');

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
// CREATE MANIPULATION FACT CARD
// ============================================

function createManipulationFactCard(finding, number) {
    const card = document.createElement('div');
    card.className = 'manipulation-fact-card';

    // Determine severity class - backend sends manipulation_severity
    const severity = finding.manipulation_severity || finding.distortion_level || 'none';
    const severityClass = getSeverityClass(severity);
    const isManipulated = finding.manipulation_detected || false;

    // Build the card HTML
    let cardHtml = `
        <div class="fact-header">
            <span class="fact-number">#${number}</span>
            <span class="fact-id">${escapeHtml(finding.fact_id || '')}</span>
            ${isManipulated ? 
                `<span class="severity-badge ${severityClass}">⚠ ${capitalizeFirst(severity)} Manipulation</span>` : 
                `<span class="severity-badge severity-none">✓ No Manipulation</span>`
            }
        </div>
        <div class="fact-statement">
            <strong>Claim:</strong> ${escapeHtml(finding.fact_statement || finding.claim || finding.statement || '')}
        </div>
    `;

    // Truthfulness score
    if (finding.truth_score !== undefined) {
        const truthPercent = Math.round(finding.truth_score * 100);
        const truthClass = finding.truth_score >= 0.7 ? 'truth-high' : finding.truth_score >= 0.4 ? 'truth-medium' : 'truth-low';
        cardHtml += `
            <div class="fact-truth">
                <strong>Truthfulness:</strong> 
                <span class="${truthClass}">${finding.truthfulness || 'Unknown'} (${truthPercent}% confidence)</span>
            </div>
        `;
    }

    // Manipulation types
    if (finding.manipulation_types && finding.manipulation_types.length > 0) {
        cardHtml += `
            <div class="fact-manipulation-types">
                <strong>Manipulation Types:</strong>
                <ul>${finding.manipulation_types.map(t => `<li>${escapeHtml(t)}</li>`).join('')}</ul>
            </div>
        `;
    }

    // What was omitted
    if (finding.what_was_omitted && finding.what_was_omitted.length > 0) {
        cardHtml += `
            <div class="fact-omitted">
                <strong>What Was Omitted:</strong>
                <ul>${finding.what_was_omitted.map(o => `<li>${escapeHtml(o)}</li>`).join('')}</ul>
            </div>
        `;
    }

    // How it serves the agenda
    if (finding.how_it_serves_agenda) {
        cardHtml += `
            <div class="fact-agenda">
                <strong>How It Serves the Agenda:</strong>
                <p>${escapeHtml(finding.how_it_serves_agenda)}</p>
            </div>
        `;
    }

    // Corrected context
    if (finding.corrected_context) {
        cardHtml += `
            <div class="fact-corrected">
                <strong>Corrected Context:</strong>
                <p>${escapeHtml(finding.corrected_context)}</p>
            </div>
        `;
    }

    // Sources used
    if (finding.sources_used && finding.sources_used.length > 0) {
        cardHtml += `
            <div class="fact-sources">
                <strong>Sources:</strong>
                <ul>${finding.sources_used.slice(0, 3).map(s => `<li><a href="${escapeHtml(s)}" target="_blank">${escapeHtml(truncateUrl(s))}</a></li>`).join('')}</ul>
            </div>
        `;
    }

    card.innerHTML = cardHtml;
    return card;
}

// ============================================
// HELPER FUNCTIONS
// ============================================

function getManipulationScoreClass(score) {
    if (score <= 3) return 'score-low';
    if (score <= 6) return 'score-medium';
    return 'score-high';
}

function getManipulationLabel(score) {
    if (score <= 2) return 'Minimal Manipulation';
    if (score <= 4) return 'Low Manipulation';
    if (score <= 6) return 'Moderate Manipulation';
    if (score <= 8) return 'High Manipulation';
    return 'Severe Manipulation';
}

function getSeverityClass(severity) {
    switch ((severity || '').toLowerCase()) {
        case 'high':
        case 'severe':
            return 'severity-high';
        case 'medium':
        case 'moderate':
            return 'severity-medium';
        case 'low':
        case 'minimal':
            return 'severity-low';
        case 'none':
            return 'severity-none';
        default:
            return 'severity-unknown';
    }
}

function getDistortionClass(level) {
    return getSeverityClass(level);
}

function capitalizeFirst(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
}

function truncateUrl(url) {
    if (!url) return '';
    try {
        const parsed = new URL(url);
        return parsed.hostname + (parsed.pathname.length > 30 ? parsed.pathname.substring(0, 30) + '...' : parsed.pathname);
    } catch {
        return url.length > 50 ? url.substring(0, 50) + '...' : url;
    }
}

// Ensure escapeHtml is available
if (typeof escapeHtml !== 'function') {
    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}