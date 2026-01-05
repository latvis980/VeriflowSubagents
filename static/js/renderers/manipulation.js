// static/js/renderers/manipulation.js - Manipulation Detection Rendering

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
    // Article Summary Section
    // ========================================
    
    const summarySection = document.getElementById('manipulationSummary');
    if (summarySection && data.article_summary) {
        const summary = data.article_summary;
        
        // Political lean badge
        const leanBadge = document.getElementById('manipPoliticalLean');
        if (leanBadge) {
            leanBadge.textContent = summary.political_lean;
            leanBadge.className = `lean-badge lean-${summary.political_lean.replace(/\s+/g, '-').toLowerCase()}`;
        }
        
        // Opinion ratio
        const ratioElement = document.getElementById('manipOpinionRatio');
        if (ratioElement) {
            const percentage = Math.round(summary.opinion_fact_ratio * 100);
            ratioElement.textContent = `${percentage}% opinion`;
            ratioElement.className = `ratio-value ${percentage > 60 ? 'high-opinion' : percentage > 30 ? 'medium-opinion' : 'low-opinion'}`;
        }
        
        // Emotional tone
        const toneElement = document.getElementById('manipEmotionalTone');
        if (toneElement) {
            toneElement.textContent = summary.emotional_tone;
        }
        
        // Main thesis
        const thesisElement = document.getElementById('manipMainThesis');
        if (thesisElement) {
            thesisElement.textContent = summary.main_thesis;
        }
        
        // Detected agenda
        const agendaElement = document.getElementById('manipDetectedAgenda');
        if (agendaElement) {
            agendaElement.textContent = summary.detected_agenda;
        }
        
        // Target audience
        const audienceElement = document.getElementById('manipTargetAudience');
        if (audienceElement) {
            audienceElement.textContent = summary.target_audience || 'Not specified';
        }
        
        // Rhetorical strategies
        const strategiesContainer = document.getElementById('manipRhetoricalStrategies');
        if (strategiesContainer && summary.rhetorical_strategies) {
            strategiesContainer.innerHTML = '';
            summary.rhetorical_strategies.forEach(strategy => {
                const tag = document.createElement('span');
                tag.className = 'strategy-tag';
                tag.textContent = strategy;
                strategiesContainer.appendChild(tag);
            });
        }
    }

    // ========================================
    // Manipulation Score Section
    // ========================================
    
    const scoreElement = document.getElementById('manipulationScore');
    if (scoreElement) {
        const score = data.manipulation_score || 0;
        scoreElement.textContent = score.toFixed(1);
        
        // Color coding based on score
        let scoreClass = 'score-low';
        if (score >= 7) {
            scoreClass = 'score-high';
        } else if (score >= 4) {
            scoreClass = 'score-medium';
        }
        scoreElement.className = `manipulation-score-value ${scoreClass}`;
    }
    
    // Score justification
    const justificationElement = document.getElementById('manipScoreJustification');
    if (justificationElement && data.report) {
        justificationElement.textContent = data.report.justification || '';
    }
    
    // Confidence
    const confidenceElement = document.getElementById('manipConfidence');
    if (confidenceElement && data.report) {
        const confidence = Math.round((data.report.confidence || 0) * 100);
        confidenceElement.textContent = `${confidence}% confidence`;
    }

    // ========================================
    // Techniques Used Section
    // ========================================
    
    const techniquesContainer = document.getElementById('manipTechniquesUsed');
    if (techniquesContainer && data.report && data.report.techniques_used) {
        techniquesContainer.innerHTML = '';
        
        if (data.report.techniques_used.length === 0) {
            techniquesContainer.innerHTML = '<p class="no-techniques">✅ No manipulation techniques detected</p>';
        } else {
            data.report.techniques_used.forEach(technique => {
                const chip = document.createElement('span');
                chip.className = 'technique-chip';
                chip.textContent = formatTechniqueName(technique);
                techniquesContainer.appendChild(chip);
            });
        }
    }

    // ========================================
    // Facts Analysis Section
    // ========================================
    
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

    // ========================================
    // What Got Right / Misleading Elements
    // ========================================
    
    // What the article got right
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
    
    // Misleading elements
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

    // ========================================
    // Recommendation Section
    // ========================================
    
    const recommendationElement = document.getElementById('manipRecommendation');
    if (recommendationElement && data.report) {
        recommendationElement.textContent = data.report.recommendation || '';
    }

    // ========================================
    // Session Info
    // ========================================
    
    const sessionIdElement = document.getElementById('manipSessionId');
    if (sessionIdElement) {
        sessionIdElement.textContent = data.session_id || '-';
    }
    
    const processingTimeElement = document.getElementById('manipProcessingTime');
    if (processingTimeElement) {
        const time = data.processing_time || 0;
        processingTimeElement.textContent = `${time.toFixed(1)}s`;
    }
    
    // R2 link
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
}


// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

function createManipulationFactCard(finding) {
    const card = document.createElement('div');
    card.className = `manipulation-fact-card ${finding.manipulation_detected ? 'has-manipulation' : 'no-manipulation'}`;
    
    // Header with fact ID and severity
    const header = document.createElement('div');
    header.className = 'fact-card-header';
    
    const factId = document.createElement('span');
    factId.className = 'fact-id';
    factId.textContent = finding.fact_id;
    header.appendChild(factId);
    
    if (finding.manipulation_detected) {
        const severityBadge = document.createElement('span');
        severityBadge.className = `severity-badge severity-${finding.manipulation_severity}`;
        severityBadge.textContent = `${finding.manipulation_severity.toUpperCase()} MANIPULATION`;
        header.appendChild(severityBadge);
    } else {
        const okBadge = document.createElement('span');
        okBadge.className = 'severity-badge severity-none';
        okBadge.textContent = 'NO MANIPULATION';
        header.appendChild(okBadge);
    }
    
    card.appendChild(header);
    
    // Fact statement
    const statement = document.createElement('div');
    statement.className = 'fact-statement';
    statement.textContent = finding.fact_statement;
    card.appendChild(statement);
    
    // Truthfulness row
    const truthRow = document.createElement('div');
    truthRow.className = 'fact-truth-row';
    
    const truthLabel = document.createElement('span');
    truthLabel.className = 'truth-label';
    truthLabel.textContent = 'Truthfulness:';
    truthRow.appendChild(truthLabel);
    
    const truthValue = document.createElement('span');
    truthValue.className = `truth-value truth-${finding.truthfulness.toLowerCase().replace('_', '-')}`;
    truthValue.textContent = `${finding.truthfulness} (${(finding.truth_score * 100).toFixed(0)}%)`;
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

function formatTechniqueName(technique) {
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
