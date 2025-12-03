// static/js/renderers/liedetection.js - Lie Detection Rendering

// ============================================
// DISPLAY LIE DETECTION RESULTS
// ============================================

function displayLieDetectionResults() {
    if (!AppState.currentLieDetectionResults || !AppState.currentLieDetectionResults.success) {
        return;
    }

    const analysis = AppState.currentLieDetectionResults.analysis;

    // Risk level
    const riskElement = document.getElementById('lieRiskLevel');
    riskElement.textContent = analysis.risk_level;
    riskElement.className = `risk-value risk-${analysis.risk_level.toLowerCase()}`;

    // Credibility score
    const scoreElement = document.getElementById('lieCredibilityScore');
    scoreElement.textContent = `${analysis.credibility_score}/100`;
    const credClass = analysis.credibility_score >= 80 ? 'high' : analysis.credibility_score >= 60 ? 'medium' : 'low';
    scoreElement.className = `credibility-value credibility-${credClass}`;

    // Overall assessment
    document.getElementById('lieOverallAssessment').textContent = analysis.overall_assessment;

    // Markers detected
    const markersContainer = document.getElementById('lieMarkersContainer');
    markersContainer.innerHTML = '';

    if (analysis.markers_detected && analysis.markers_detected.length > 0) {
        analysis.markers_detected.forEach(marker => {
            const markerCard = createMarkerCard(marker);
            markersContainer.appendChild(markerCard);
        });
    } else {
        markersContainer.innerHTML = '<p class="no-markers">✅ No significant deception markers detected.</p>';
    }

    // Positive indicators
    const positiveContainer = document.getElementById('liePositiveIndicators');
    positiveContainer.innerHTML = '';

    if (analysis.positive_indicators && analysis.positive_indicators.length > 0) {
        const list = document.createElement('ul');
        list.className = 'positive-list';
        analysis.positive_indicators.forEach(indicator => {
            const li = document.createElement('li');
            li.textContent = indicator;
            list.appendChild(li);
        });
        positiveContainer.appendChild(list);
    } else {
        positiveContainer.innerHTML = '<p>No positive indicators documented.</p>';
    }

    // Conclusion and reasoning
    document.getElementById('lieConclusion').textContent = analysis.conclusion;
    document.getElementById('lieDetailedReasoning').textContent = analysis.reasoning;

    // Session info
    document.getElementById('lieSessionId').textContent = AppState.currentLieDetectionResults.session_id || '-';
    document.getElementById('lieProcessingTime').textContent = Math.round(AppState.currentLieDetectionResults.processing_time || 0) + 's';

    // R2 link
    if (AppState.currentLieDetectionResults.r2_url) {
        const link = document.getElementById('lieR2Link');
        link.href = AppState.currentLieDetectionResults.r2_url;
        link.style.display = 'inline';
        document.getElementById('lieR2Sep').style.display = 'inline';
    } else {
        document.getElementById('lieR2Link').style.display = 'none';
        document.getElementById('lieR2Sep').style.display = 'none';
    }
}

// ============================================
// CREATE MARKER CARD
// ============================================

function createMarkerCard(marker) {
    const card = document.createElement('div');
    card.className = `marker-card severity-${marker.severity.toLowerCase()}`;

    const examplesList = marker.examples.map(ex => `<li>${escapeHtml(ex)}</li>`).join('');

    card.innerHTML = `
        <div class="marker-header">
            <h4>${escapeHtml(marker.category)}</h4>
            <span class="severity-badge">${marker.severity}</span>
        </div>
        <div class="marker-explanation">${escapeHtml(marker.explanation)}</div>
        <div class="marker-examples">
            <strong>Examples from text:</strong>
            <ul>${examplesList}</ul>
        </div>
    `;

    return card;
}
