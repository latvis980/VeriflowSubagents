// static/js/renderers/liedetection.js - Lie Detection Rendering
// VeriFlow Redesign - Minimalist Theme (FIXED)

// ============================================
// DISPLAY LIE DETECTION RESULTS
// ============================================

function displayLieDetectionResults() {
    if (!AppState.currentLieDetectionResults || !AppState.currentLieDetectionResults.success) {
        console.error('No lie detection results available');
        return;
    }

    console.log('Displaying Lie Detection Results:', AppState.currentLieDetectionResults);

    const data = AppState.currentLieDetectionResults;
    const analysis = data.analysis || data;

    // Score display (credibility score - 0-100 where 100 = highly credible)
    const scoreElement = document.getElementById('lieScore');
    if (scoreElement) {
        const score = analysis.credibility_score || 0;
        scoreElement.textContent = score;
        scoreElement.className = `lie-score-value ${getLieScoreClass(score)}`;
    }

    // Verdict/Risk level
    const verdictElement = document.getElementById('lieVerdict');
    if (verdictElement) {
        const riskLevel = analysis.risk_level || 'Unknown';
        verdictElement.textContent = `${riskLevel.toUpperCase()} RISK`;
        verdictElement.className = `lie-verdict risk-${riskLevel.toLowerCase()}`;
    }

    // Overall Assessment (summary)
    const justificationElement = document.getElementById('lieJustification');
    if (justificationElement) {
        justificationElement.textContent = analysis.overall_assessment || '';
    }

    // Markers detected - THE MAIN FIX
    const markersContainer = document.getElementById('lieIndicators');
    if (markersContainer) {
        markersContainer.innerHTML = '';

        if (analysis.markers_detected && analysis.markers_detected.length > 0) {
            analysis.markers_detected.forEach(marker => {
                // Only show markers that are present (present: true)
                if (marker.present !== false) {
                    markersContainer.appendChild(createMarkerCard(marker));
                }
            });
            // If no markers were actually present after filtering
            if (markersContainer.children.length === 0) {
                markersContainer.innerHTML = '<p class="no-markers">No significant deception markers detected.</p>';
            }
        } else {
            markersContainer.innerHTML = '<p class="no-markers">No significant deception markers detected.</p>';
        }
    }

    // Positive/Credibility Indicators
    const positiveContainer = document.getElementById('liePositiveIndicators');
    if (positiveContainer) {
        positiveContainer.innerHTML = '';

        if (analysis.positive_indicators && analysis.positive_indicators.length > 0) {
            const list = createPositiveIndicatorsList(analysis.positive_indicators);
            positiveContainer.appendChild(list);
        } else {
            positiveContainer.innerHTML = '<p class="no-indicators">No positive credibility indicators documented.</p>';
        }
    }

    // Conclusion
    const conclusionElement = document.getElementById('lieConclusion');
    if (conclusionElement) {
        conclusionElement.textContent = analysis.conclusion || 'No conclusion available.';
    }

    // Detailed Reasoning
    const reasoningElement = document.getElementById('lieDetailedReasoning');
    if (reasoningElement) {
        reasoningElement.textContent = analysis.reasoning || 'No detailed reasoning available.';
    }

    // Session info
    const sessionId = document.getElementById('lieSessionId');
    const processingTime = document.getElementById('lieProcessingTime');

    if (sessionId) sessionId.textContent = data.session_id || '-';
    if (processingTime) processingTime.textContent = Math.round(data.processing_time || 0) + 's';

    // R2 link
    const r2Link = document.getElementById('lieR2Link');
    const r2Sep = document.getElementById('lieR2Sep');

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
// CREATE MARKER CARD - FIXED VERSION
// ============================================
// Backend MarkerCategory schema:
//   category: str (marker category name)
//   present: bool
//   severity: str (LOW, MEDIUM, HIGH)
//   examples: List[str] (specific examples from text)
//   explanation: str (why this matters)

function createMarkerCard(marker) {
    const card = document.createElement('div');

    const severity = (marker.severity || 'medium').toLowerCase();
    card.className = `marker-card severity-${severity}`;

    // Build examples list - marker.examples is an ARRAY
    let examplesHtml = '';
    if (marker.examples && Array.isArray(marker.examples) && marker.examples.length > 0) {
        const exampleItems = marker.examples
            .map(ex => `<li>"${escapeHtml(ex)}"</li>`)
            .join('');
        examplesHtml = `
            <div class="marker-examples">
                <span class="examples-label">Examples from text:</span>
                <ul class="examples-list">${exampleItems}</ul>
            </div>
        `;
    }

    card.innerHTML = `
        <div class="marker-header">
            <span class="marker-type">${escapeHtml(marker.category || 'Unknown Marker')}</span>
            <span class="marker-severity ${getSeverityClass(severity)}">${severity.toUpperCase()}</span>
        </div>
        <div class="marker-explanation">${escapeHtml(marker.explanation || '')}</div>
        ${examplesHtml}
    `;

    return card;
}

// ============================================
// CREATE POSITIVE INDICATORS LIST
// ============================================

function createPositiveIndicatorsList(indicators) {
    const list = document.createElement('ul');
    list.className = 'credibility-list';

    indicators.forEach(indicator => {
        const li = document.createElement('li');
        const text = typeof indicator === 'string' 
            ? indicator 
            : (indicator.description || indicator.text || String(indicator));
        li.textContent = text;
        list.appendChild(li);
    });

    return list;
}

// ============================================
// HELPER FUNCTIONS
// ============================================

function getLieScoreClass(score) {
    // Score is credibility (0-100, higher = more credible)
    if (score >= 70) return 'score-high';      // Good credibility
    if (score >= 40) return 'score-medium';    // Mixed signals
    return 'score-low';                         // Low credibility
}

function getSeverityClass(severity) {
    switch (severity.toLowerCase()) {
        case 'high':
        case 'critical':
            return 'severity-high';
        case 'medium':
        case 'moderate':
            return 'severity-medium';
        case 'low':
        default:
            return 'severity-low';
    }
}

function capitalizeFirst(str) {
    if (!str) return '';
    return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
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