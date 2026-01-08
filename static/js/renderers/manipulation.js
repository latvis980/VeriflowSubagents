// static/js/renderers/manipulation.js - Manipulation Detection Rendering
// UPDATED: Two-tab layout with Summary (narrative) and Facts (detailed) tabs

// ============================================================================
// INNER TAB SWITCHING FOR MANIPULATION RESULTS
// ============================================================================

function initManipulationTabs() {
    const summaryTab = document.getElementById('manipSummaryTab');
    const factsTab = document.getElementById('manipFactsTab');
    const summaryContent = document.getElementById('manipSummaryContent');
    const factsContent = document.getElementById('manipFactsContent');

    if (summaryTab) {
        summaryTab.addEventListener('click', () => {
            summaryTab.classList.add('active');
            factsTab.classList.remove('active');
            summaryContent.style.display = 'block';
            factsContent.style.display = 'none';
        });
    }

    if (factsTab) {
        factsTab.addEventListener('click', () => {
            factsTab.classList.add('active');
            summaryTab.classList.remove('active');
            factsContent.style.display = 'block';
            summaryContent.style.display = 'none';
        });
    }
}

// Initialize tabs when DOM is ready
document.addEventListener('DOMContentLoaded', initManipulationTabs);

// ============================================================================
// DISPLAY MANIPULATION RESULTS
// ============================================================================

function displayManipulationResults() {
    if (!AppState.currentManipulationResults || !AppState.currentManipulationResults.success) {
        console.error('No manipulation results to display');
        return;
    }

    const data = AppState.currentManipulationResults;

    // ========================================
    // SUMMARY TAB - Score Display
    // ========================================

    const scoreElement = document.getElementById('manipulationScore');
    if (scoreElement) {
        const score = data.manipulation_score || 0;
        scoreElement.textContent = score.toFixed(1);

        let scoreClass = 'score-low';
        if (score >= 7) {
            scoreClass = 'score-high';
        } else if (score >= 4) {
            scoreClass = 'score-medium';
        }
        scoreElement.className = `manipulation-score-value ${scoreClass}`;
    }

    // Score Label
    const scoreLabelElement = document.getElementById('manipScoreLabel');
    if (scoreLabelElement) {
        const score = data.manipulation_score || 0;
        let label = 'Low Manipulation';
        if (score >= 7) {
            label = 'High Manipulation';
        } else if (score >= 4) {
            label = 'Moderate Manipulation';
        }
        scoreLabelElement.textContent = label;
    }

    // Confidence
    const confidenceElement = document.getElementById('manipConfidence');
    if (confidenceElement && data.report) {
        const confidence = Math.round((data.report.confidence || 0) * 100);
        confidenceElement.textContent = `${confidence}% confidence`;
    }

    // ========================================
    // Narrative Summary (Main Human-like Analysis)
    // ========================================

    const narrativeContainer = document.getElementById('manipNarrativeSummary');
    if (narrativeContainer) {
        // Use backend-generated narrative if available, otherwise generate one
        let narrative = '';
        if (data.report && data.report.narrative_summary) {
            narrative = data.report.narrative_summary;
        } else {
            narrative = generateNarrativeSummary(data);
        }
        narrativeContainer.innerHTML = `<p class="narrative-text">${escapeHtml(narrative)}</p>`;
    }

    // Quick Meta Info (compact display)
    const metaContainer = document.getElementById('manipQuickMeta');
    if (metaContainer && data.article_summary) {
        const summary = data.article_summary;
        metaContainer.innerHTML = `
            <span class="meta-chip lean-${(summary.political_lean || '').replace(/\s+/g, '-').toLowerCase()}">
                <strong>Lean:</strong> ${escapeHtml(summary.political_lean || 'Unknown')}
            </span>
            <span class="meta-chip">
                <strong>Tone:</strong> ${escapeHtml(summary.emotional_tone || 'Unknown')}
            </span>
            <span class="meta-chip">
                <strong>Opinion:</strong> ${Math.round((summary.opinion_fact_ratio || 0) * 100)}%
            </span>
        `;
    }

    // Techniques Used (compact list in summary)
    const techniquesSummary = document.getElementById('manipTechniquesSummary');
    if (techniquesSummary && data.report && data.report.techniques_used) {
        if (data.report.techniques_used.length === 0) {
            techniquesSummary.innerHTML = '<span class="no-techniques-inline">✅ No manipulation techniques detected</span>';
        } else {
            techniquesSummary.innerHTML = data.report.techniques_used
                .map(t => `<span class="technique-chip-small">${formatTechniqueName(t)}</span>`)
                .join('');
        }
    }

    // Key Takeaways (What Got Right + Misleading - combined in summary)
    const takeawaysContainer = document.getElementById('manipKeyTakeaways');
    if (takeawaysContainer && data.report) {
        let takeawaysHTML = '';

        // What's accurate
        if (data.report.what_got_right && data.report.what_got_right.length > 0) {
            takeawaysHTML += '<div class="takeaway-section takeaway-positive">';
            takeawaysHTML += '<strong>✅ What\'s accurate:</strong> ';
            takeawaysHTML += data.report.what_got_right.slice(0, 2).map(item => escapeHtml(item)).join('; ');
            if (data.report.what_got_right.length > 2) {
                takeawaysHTML += ` <em>(+${data.report.what_got_right.length - 2} more in Facts tab)</em>`;
            }
            takeawaysHTML += '</div>';
        }

        // What's misleading
        if (data.report.misleading_elements && data.report.misleading_elements.length > 0) {
            takeawaysHTML += '<div class="takeaway-section takeaway-warning">';
            takeawaysHTML += '<strong>⚠️ Watch out for:</strong> ';
            takeawaysHTML += data.report.misleading_elements.slice(0, 2).map(item => escapeHtml(item)).join('; ');
            if (data.report.misleading_elements.length > 2) {
                takeawaysHTML += ` <em>(+${data.report.misleading_elements.length - 2} more in Facts tab)</em>`;
            }
            takeawaysHTML += '</div>';
        }

        takeawaysContainer.innerHTML = takeawaysHTML || '<p class="no-takeaways">No specific takeaways identified</p>';
    }

    // Recommendation
    const recommendationElement = document.getElementById('manipRecommendationSummary');
    if (recommendationElement && data.report && data.report.recommendation) {
        recommendationElement.textContent = data.report.recommendation;
    }

    // ========================================
    // FACTS TAB - Detailed Analysis
    // ========================================

    // Article Summary Section (detailed in facts tab)
    const summarySection = document.getElementById('manipArticleSummaryDetailed');
    if (summarySection && data.article_summary) {
        const summary = data.article_summary;

        let detailsHTML = `
            <div class="summary-detail-grid">
                <div class="detail-item">
                    <span class="detail-label">Political Lean</span>
                    <span class="lean-badge lean-${(summary.political_lean || '').replace(/\s+/g, '-').toLowerCase()}">${escapeHtml(summary.political_lean || 'Unknown')}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Opinion Ratio</span>
                    <span class="ratio-value">${Math.round((summary.opinion_fact_ratio || 0) * 100)}% opinion</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Emotional Tone</span>
                    <span>${escapeHtml(summary.emotional_tone || 'Unknown')}</span>
                </div>
                <div class="detail-item">
                    <span class="detail-label">Target Audience</span>
                    <span>${escapeHtml(summary.target_audience || 'Not specified')}</span>
                </div>
            </div>
            <div class="summary-detail-section">
                <strong>Main Thesis:</strong>
                <p>${escapeHtml(summary.main_thesis || 'Not identified')}</p>
            </div>
            <div class="summary-detail-section">
                <strong>Detected Agenda:</strong>
                <p>${escapeHtml(summary.detected_agenda || 'Not identified')}</p>
            </div>
        `;

        if (summary.rhetorical_strategies && summary.rhetorical_strategies.length > 0) {
            detailsHTML += `
                <div class="summary-detail-section">
                    <strong>Rhetorical Strategies:</strong>
                    <div class="strategies-container">
                        ${summary.rhetorical_strategies.map(s => `<span class="strategy-tag">${escapeHtml(s)}</span>`).join('')}
                    </div>
                </div>
            `;
        }

        summarySection.innerHTML = detailsHTML;
    }

    // Techniques Used (detailed in facts tab)
    const techniquesDetailed = document.getElementById('manipTechniquesDetailed');
    if (techniquesDetailed && data.report && data.report.techniques_used) {
        if (data.report.techniques_used.length === 0) {
            techniquesDetailed.innerHTML = '<p class="no-techniques">✅ No manipulation techniques detected</p>';
        } else {
            techniquesDetailed.innerHTML = data.report.techniques_used
                .map(technique => `<span class="technique-chip">${formatTechniqueName(technique)}</span>`)
                .join('');
        }
    }

    // Facts Analysis Section
    const factsContainer = document.getElementById('manipFactsList');
    if (factsContainer && data.manipulation_findings) {
        factsContainer.innerHTML = '';

        if (data.manipulation_findings.length === 0) {
            factsContainer.innerHTML = '<p class="no-facts">No facts were analyzed</p>';
        } else {
            data.manipulation_findings.forEach(finding => {
                const factCard = createManipulationFactCard(finding);
                factsContainer.appendChild(factCard);
            });
        }
    }

    // What Got Right (detailed)
    const rightContainer = document.getElementById('manipWhatGotRight');
    if (rightContainer && data.report && data.report.what_got_right) {
        rightContainer.innerHTML = '';

        if (data.report.what_got_right.length === 0) {
            rightContainer.innerHTML = '<p class="empty-list">No positive elements identified</p>';
        } else {
            const list = document.createElement('ul');
            list.className = 'got-right-list';
            data.report.what_got_right.forEach(item => {
                const li = document.createElement('li');
                li.innerHTML = `<span class="check-icon">✓</span> ${escapeHtml(item)}`;
                list.appendChild(li);
            });
            rightContainer.appendChild(list);
        }
    }

    // Misleading elements (detailed)
    const misleadingContainer = document.getElementById('manipMisleadingElements');
    if (misleadingContainer && data.report && data.report.misleading_elements) {
        misleadingContainer.innerHTML = '';

        if (data.report.misleading_elements.length === 0) {
            misleadingContainer.innerHTML = '<p class="empty-list">No misleading elements identified</p>';
        } else {
            const list = document.createElement('ul');
            list.className = 'misleading-list';
            data.report.misleading_elements.forEach(item => {
                const li = document.createElement('li');
                li.innerHTML = `<span class="warning-icon">⚠️</span> ${escapeHtml(item)}`;
                list.appendChild(li);
            });
            misleadingContainer.appendChild(list);
        }
    }

    // Recommendation (detailed)
    const recommendationDetailed = document.getElementById('manipRecommendationDetailed');
    if (recommendationDetailed && data.report && data.report.recommendation) {
        recommendationDetailed.textContent = data.report.recommendation;
    }

    // Session Info
    const sessionIdElement = document.getElementById('manipSessionId');
    if (sessionIdElement) {
        sessionIdElement.textContent = data.session_id || '-';
    }

    const processingTimeElement = document.getElementById('manipProcessingTime');
    if (processingTimeElement) {
        processingTimeElement.textContent = data.processing_time 
            ? `${data.processing_time.toFixed(1)}s` 
            : '-';
    }

    // R2 Link
    const r2Link = document.getElementById('manipR2Link');
    const r2Sep = document.getElementById('manipR2Sep');
    if (r2Link && data.r2_url) {
        r2Link.href = data.r2_url;
        r2Link.style.display = 'inline';
        if (r2Sep) r2Sep.style.display = 'inline';
    } else if (r2Link) {
        r2Link.style.display = 'none';
        if (r2Sep) r2Sep.style.display = 'none';
    }

    // Show summary tab by default
    const summaryTab = document.getElementById('manipSummaryTab');
    const factsTab = document.getElementById('manipFactsTab');
    const summaryContent = document.getElementById('manipSummaryContent');
    const factsContent = document.getElementById('manipFactsContent');

    if (summaryTab) summaryTab.classList.add('active');
    if (factsTab) factsTab.classList.remove('active');
    if (summaryContent) summaryContent.style.display = 'block';
    if (factsContent) factsContent.style.display = 'none';
}

// ============================================================================
// GENERATE NARRATIVE SUMMARY (Fallback if backend doesn't provide one)
// ============================================================================

function generateNarrativeSummary(data) {
    const score = data.manipulation_score || 0;
    const summary = data.article_summary || {};
    const report = data.report || {};

    let narrative = '';

    // Opening based on score
    if (score >= 7) {
        narrative = `This article shows significant signs of manipulation. `;
    } else if (score >= 4) {
        narrative = `This article contains some elements that could be considered manipulative. `;
    } else {
        narrative = `This article appears to be relatively balanced in its presentation. `;
    }

    // Add political lean context
    if (summary.political_lean && summary.political_lean.toLowerCase() !== 'center') {
        narrative += `The content leans ${summary.political_lean.toLowerCase()}, `;
    }

    // Add thesis and agenda
    if (summary.main_thesis) {
        narrative += `with a central argument that ${summary.main_thesis.toLowerCase().replace(/\.$/, '')}. `;
    }

    if (summary.detected_agenda) {
        narrative += `The underlying agenda appears to be: ${summary.detected_agenda.toLowerCase().replace(/\.$/, '')}. `;
    }

    // Techniques summary
    if (report.techniques_used && report.techniques_used.length > 0) {
        const techniqueNames = report.techniques_used.slice(0, 3).map(t => formatTechniqueName(t).toLowerCase());
        narrative += `Key techniques used include ${techniqueNames.join(', ')}. `;
    }

    // Add justification if available
    if (report.justification) {
        narrative += report.justification;
    }

    return narrative;
}

// ============================================================================
// CREATE MANIPULATION FACT CARD
// ============================================================================

function createManipulationFactCard(finding) {
    const card = document.createElement('div');
    card.className = 'manipulation-fact-card';

    // Determine status class and header
    let statusClass = 'status-neutral';
    let statusIcon = '📋';
    let statusLabel = 'Analyzed';

    if (finding.manipulation_detected) {
        statusClass = 'status-manipulated';
        statusIcon = '⚠️';
        statusLabel = 'Manipulation Detected';
    } else if (finding.truthfulness === 'TRUE') {
        statusClass = 'status-verified';
        statusIcon = '✅';
        statusLabel = 'Verified True';
    } else if (finding.truthfulness === 'FALSE') {
        statusClass = 'status-false';
        statusIcon = '❌';
        statusLabel = 'False';
    } else if (finding.truthfulness === 'PARTIALLY_TRUE') {
        statusClass = 'status-partial';
        statusIcon = '⚡';
        statusLabel = 'Partially True';
    }

    card.classList.add(statusClass);

    // Header row
    const header = document.createElement('div');
    header.className = 'fact-header';
    header.innerHTML = `
        <span class="fact-id">${escapeHtml(finding.fact_id || '')}</span>
        <span class="fact-status-badge ${statusClass}">${statusIcon} ${statusLabel}</span>
    `;
    card.appendChild(header);

    // Fact statement
    const statement = document.createElement('div');
    statement.className = 'fact-statement';
    statement.innerHTML = `<strong>Claim:</strong> ${escapeHtml(finding.fact_statement || '')}`;
    card.appendChild(statement);

    // Truthfulness row
    const truthRow = document.createElement('div');
    truthRow.className = 'fact-truth-row';

    const truthLabel = document.createElement('span');
    truthLabel.className = 'truth-label';
    truthLabel.textContent = 'Truthfulness: ';
    truthRow.appendChild(truthLabel);

    const truthValue = document.createElement('span');
    truthValue.className = `truth-value truth-${(finding.truthfulness || '').toLowerCase().replace('_', '-')}`;
    truthValue.textContent = `${finding.truthfulness || 'Unknown'} (${((finding.truth_score || 0) * 100).toFixed(0)}%)`;
    truthRow.appendChild(truthValue);

    card.appendChild(truthRow);

    // If manipulation detected, show details
    if (finding.manipulation_detected) {
        // Manipulation types
        if (finding.manipulation_types && finding.manipulation_types.length > 0) {
            const typesRow = document.createElement('div');
            typesRow.className = 'manipulation-types-row';

            const typesLabel = document.createElement('span');
            typesLabel.className = 'types-label';
            typesLabel.textContent = 'Manipulation types:';
            typesRow.appendChild(typesLabel);

            const typesContainer = document.createElement('div');
            typesContainer.className = 'types-container';
            finding.manipulation_types.forEach(type => {
                const chip = document.createElement('span');
                chip.className = 'type-chip';
                chip.textContent = formatTechniqueName(type);
                typesContainer.appendChild(chip);
            });
            typesRow.appendChild(typesContainer);

            card.appendChild(typesRow);
        }

        // What was omitted
        if (finding.what_was_omitted && finding.what_was_omitted.length > 0) {
            const omittedSection = document.createElement('div');
            omittedSection.className = 'omitted-section';

            const omittedLabel = document.createElement('div');
            omittedLabel.className = 'omitted-label';
            omittedLabel.textContent = '📌 Context that was omitted:';
            omittedSection.appendChild(omittedLabel);

            const omittedList = document.createElement('ul');
            omittedList.className = 'omitted-list';
            finding.what_was_omitted.forEach(item => {
                const li = document.createElement('li');
                li.textContent = item;
                omittedList.appendChild(li);
            });
            omittedSection.appendChild(omittedList);

            card.appendChild(omittedSection);
        }

        // How it serves agenda
        if (finding.how_it_serves_agenda) {
            const agendaSection = document.createElement('div');
            agendaSection.className = 'agenda-section';

            const agendaLabel = document.createElement('div');
            agendaLabel.className = 'agenda-label';
            agendaLabel.textContent = '🎯 How it serves the agenda:';
            agendaSection.appendChild(agendaLabel);

            const agendaText = document.createElement('p');
            agendaText.className = 'agenda-text';
            agendaText.textContent = finding.how_it_serves_agenda;
            agendaSection.appendChild(agendaText);

            card.appendChild(agendaSection);
        }

        // Corrected context
        if (finding.corrected_context) {
            const correctedSection = document.createElement('div');
            correctedSection.className = 'corrected-section';

            const correctedLabel = document.createElement('div');
            correctedLabel.className = 'corrected-label';
            correctedLabel.textContent = '✅ Corrected understanding:';
            correctedSection.appendChild(correctedLabel);

            const correctedText = document.createElement('p');
            correctedText.className = 'corrected-text';
            correctedText.textContent = finding.corrected_context;
            correctedSection.appendChild(correctedText);

            card.appendChild(correctedSection);
        }
    }

    // Sources used (collapsible)
    if (finding.sources_used && finding.sources_used.length > 0) {
        const sourcesSection = document.createElement('details');
        sourcesSection.className = 'sources-section';

        const sourcesSummary = document.createElement('summary');
        sourcesSummary.textContent = `📚 Sources used (${finding.sources_used.length})`;
        sourcesSection.appendChild(sourcesSummary);

        const sourcesList = document.createElement('ul');
        sourcesList.className = 'sources-list';
        finding.sources_used.forEach(url => {
            const li = document.createElement('li');
            const link = document.createElement('a');
            link.href = url;
            link.target = '_blank';
            link.textContent = truncateUrl(url);
            li.appendChild(link);
            sourcesList.appendChild(li);
        });
        sourcesSection.appendChild(sourcesList);

        card.appendChild(sourcesSection);
    }

    return card;
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

function formatTechniqueName(technique) {
    if (!technique) return '';
    // Convert snake_case or lowercase to Title Case
    return technique
        .replace(/_/g, ' ')
        .replace(/\b\w/g, l => l.toUpperCase());
}

function truncateUrl(url) {
    try {
        const urlObj = new URL(url);
        const path = urlObj.pathname;
        if (path.length > 40) {
            return urlObj.hostname + path.substring(0, 37) + '...';
        }
        return urlObj.hostname + path;
    } catch {
        return url.length > 50 ? url.substring(0, 47) + '...' : url;
    }
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}


// ============================================================================
// SCORE VISUALIZATION (optional gauge)
// ============================================================================

function renderManipulationGauge(score, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // Calculate rotation (0-10 maps to -90 to 90 degrees)
    const rotation = (score / 10) * 180 - 90;

    // Determine color based on score
    let color = '#22c55e'; // green
    if (score >= 7) {
        color = '#ef4444'; // red
    } else if (score >= 4) {
        color = '#f59e0b'; // amber
    }

    container.innerHTML = `
        <div class="gauge-container">
            <svg viewBox="0 0 100 60" class="gauge-svg">
                <!-- Background arc -->
                <path d="M 10 50 A 40 40 0 0 1 90 50" 
                      fill="none" 
                      stroke="#e5e7eb" 
                      stroke-width="8"
                      stroke-linecap="round"/>
                <!-- Value arc -->
                <path d="M 10 50 A 40 40 0 0 1 90 50" 
                      fill="none" 
                      stroke="${color}" 
                      stroke-width="8"
                      stroke-linecap="round"
                      stroke-dasharray="${score * 12.56} 125.6"
                      class="gauge-value"/>
                <!-- Needle -->
                <line x1="50" y1="50" x2="50" y2="15" 
                      stroke="#1f2937" 
                      stroke-width="2"
                      stroke-linecap="round"
                      transform="rotate(${rotation} 50 50)"
                      class="gauge-needle"/>
                <!-- Center dot -->
                <circle cx="50" cy="50" r="4" fill="#1f2937"/>
            </svg>
            <div class="gauge-labels">
                <span class="gauge-min">0</span>
                <span class="gauge-max">10</span>
            </div>
        </div>
    `;
}