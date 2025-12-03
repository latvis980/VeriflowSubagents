// static/js/renderers/bias.js - Bias Analysis Rendering

// ============================================
// DISPLAY BIAS RESULTS
// ============================================

function displayBiasResults() {
    if (!AppState.currentBiasResults || !AppState.currentBiasResults.success) {
        return;
    }

    const analysis = AppState.currentBiasResults.analysis;

    const score = analysis.consensus_bias_score || 0;
    const direction = analysis.consensus_direction || 'Unknown';
    const confidence = analysis.confidence || 0;

    document.getElementById('consensusBiasScore').textContent = score.toFixed(1) + '/10';
    document.getElementById('consensusBiasDirection').textContent = direction;
    document.getElementById('biasConfidence').textContent = Math.round(confidence * 100) + '%';

    document.getElementById('biasSessionId').textContent = AppState.currentBiasResults.session_id || '-';
    document.getElementById('biasProcessingTime').textContent = Math.round(AppState.currentBiasResults.processing_time || 0) + 's';

    displayModelAnalysis('gpt', analysis.gpt_analysis);
    displayModelAnalysis('claude', analysis.claude_analysis);
    displayConsensusAnalysis(analysis);
}

// ============================================
// DISPLAY MODEL ANALYSIS
// ============================================

function displayModelAnalysis(model, data) {
    if (!data) return;

    const prefix = model === 'gpt' ? 'gpt' : 'claude';

    document.getElementById(`${prefix}OverallAssessment`).textContent = data.reasoning || '-';

    const indicatorsList = document.getElementById(`${prefix}BiasIndicators`);
    indicatorsList.innerHTML = '';

    if (data.biases_detected && data.biases_detected.length > 0) {
        data.biases_detected.forEach(bias => {
            const li = document.createElement('li');
            li.innerHTML = `<strong>${bias.type}</strong> (${bias.severity}/10): ${bias.evidence}`;
            indicatorsList.appendChild(li);
        });
    } else {
        indicatorsList.innerHTML = '<li>No significant bias indicators detected</li>';
    }

    const languageText = data.balanced_aspects ? data.balanced_aspects.join(' • ') : 'Analysis complete';
    document.getElementById(`${prefix}LanguageAnalysis`).textContent = languageText;
}

// ============================================
// DISPLAY CONSENSUS ANALYSIS
// ============================================

function displayConsensusAnalysis(analysis) {
    const agreementList = document.getElementById('areasOfAgreement');
    agreementList.innerHTML = '';
    (analysis.areas_of_agreement || []).forEach(item => {
        const li = document.createElement('li');
        li.textContent = item;
        agreementList.appendChild(li);
    });

    const disagreementList = document.getElementById('areasOfDisagreement');
    disagreementList.innerHTML = '';
    (analysis.areas_of_disagreement || []).forEach(item => {
        const li = document.createElement('li');
        li.textContent = item;
        disagreementList.appendChild(li);
    });

    document.getElementById('finalAssessment').textContent = analysis.final_assessment || '-';

    const recommendationsList = document.getElementById('recommendations');
    recommendationsList.innerHTML = '';
    (analysis.recommendations || []).forEach(rec => {
        const li = document.createElement('li');
        li.textContent = rec;
        recommendationsList.appendChild(li);
    });
}

// ============================================
// MODEL TAB SWITCHING FOR BIAS ANALYSIS
// ============================================

function initBiasModelTabs() {
    modelTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            // Update active tab styling
            modelTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            // Get selected model
            const model = tab.dataset.model;

            // Show/hide the correct analysis panel
            const gptAnalysis = document.getElementById('gptAnalysis');
            const claudeAnalysis = document.getElementById('claudeAnalysis');
            const consensusAnalysis = document.getElementById('consensusAnalysis');

            if (gptAnalysis) {
                gptAnalysis.style.display = model === 'gpt' ? 'block' : 'none';
            }
            if (claudeAnalysis) {
                claudeAnalysis.style.display = model === 'claude' ? 'block' : 'none';
            }
            if (consensusAnalysis) {
                consensusAnalysis.style.display = model === 'consensus' ? 'block' : 'none';
            }
        });
    });
}
