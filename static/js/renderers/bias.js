// static/js/renderers/bias.js - Bias Analysis Rendering
// VeriFlow Redesign - Minimalist Theme
// FIXED: Access nested 'analysis' object, use correct element IDs, add model tab switching

// ============================================
// INITIALIZE MODEL TAB SWITCHING
// ============================================

document.addEventListener('DOMContentLoaded', function() {
    // Model tab switching for bias analysis
    const modelTabs = document.querySelectorAll('.model-tabs .model-tab');

    modelTabs.forEach(tab => {
        tab.addEventListener('click', function() {
            const model = this.dataset.model;

            // Update active tab
            modelTabs.forEach(t => t.classList.remove('active'));
            this.classList.add('active');

            // Show corresponding analysis panel
            document.getElementById('gptAnalysis').style.display = model === 'gpt' ? 'block' : 'none';
            document.getElementById('claudeAnalysis').style.display = model === 'claude' ? 'block' : 'none';
            document.getElementById('consensusAnalysis').style.display = model === 'consensus' ? 'block' : 'none';
        });
    });
});

// ============================================
// DISPLAY BIAS RESULTS
// ============================================

function displayBiasResults() {
    console.log('displayBiasResults called');
    console.log('AppState.currentBiasResults:', AppState.currentBiasResults);

    if (!AppState.currentBiasResults) {
        console.error('No bias results in AppState');
        return;
    }

    if (!AppState.currentBiasResults.success) {
        console.error('Bias results success is false:', AppState.currentBiasResults);
        return;
    }

    const data = AppState.currentBiasResults;

    // FIX: Access the nested 'analysis' object - backend wraps everything in 'analysis'
    const analysis = data.analysis;

    if (!analysis) {
        console.error('No analysis object in bias results. Data structure:', Object.keys(data));
        return;
    }

    console.log('Analysis object keys:', Object.keys(analysis));

    // Display GPT analysis
    if (analysis.gpt_analysis) {
        console.log('Displaying GPT analysis');
        displayModelAnalysis('gpt', analysis.gpt_analysis);
    } else {
        console.warn('No gpt_analysis in analysis object');
    }

    // Display Claude analysis
    if (analysis.claude_analysis) {
        console.log('Displaying Claude analysis');
        displayModelAnalysis('claude', analysis.claude_analysis);
    } else {
        console.warn('No claude_analysis in analysis object');
    }

    // Display Consensus analysis - FIX: use 'combined_report' not 'consensus'
    if (analysis.combined_report) {
        console.log('Displaying Consensus analysis from combined_report');
        displayConsensusAnalysis(analysis.combined_report);
    } else {
        console.warn('No combined_report in analysis object');
    }

    // Session info - FIX: use shared element IDs (not bias-prefixed)
    const sessionId = document.getElementById('sessionId');
    const processingTime = document.getElementById('processingTime');

    if (sessionId) sessionId.textContent = data.session_id || '-';
    if (processingTime) processingTime.textContent = Math.round(data.processing_time || 0) + 's';

    // R2 link - FIX: use shared element IDs
    const r2Link = document.getElementById('r2Link');
    const r2Sep = document.getElementById('r2Sep');

    if (r2Link && r2Sep) {
        if (data.r2_upload && data.r2_upload.links && data.r2_upload.links.length > 0) {
            r2Link.href = data.r2_upload.links[0];  // First link is combined report
            r2Link.style.display = 'inline';
            r2Sep.style.display = 'inline';
        } else {
            r2Link.style.display = 'none';
            r2Sep.style.display = 'none';
        }
    }

    // Reset to GPT tab as default view
    const modelTabs = document.querySelectorAll('.model-tabs .model-tab');
    modelTabs.forEach(t => t.classList.remove('active'));
    const gptTab = document.querySelector('.model-tab[data-model="gpt"]');
    if (gptTab) gptTab.classList.add('active');

    document.getElementById('gptAnalysis').style.display = 'block';
    document.getElementById('claudeAnalysis').style.display = 'none';
    document.getElementById('consensusAnalysis').style.display = 'none';
}

// ============================================
// DISPLAY MODEL ANALYSIS (GPT or Claude)
// ============================================

function displayModelAnalysis(model, modelAnalysis) {
    console.log(`displayModelAnalysis for ${model}:`, modelAnalysis);

    const prefix = model === 'gpt' ? 'gpt' : 'claude';

    // Score
    const scoreEl = document.getElementById(`${prefix}BiasScore`);
    if (scoreEl) {
        const score = modelAnalysis.bias_score || modelAnalysis.score || 0;
        scoreEl.textContent = score.toFixed ? score.toFixed(1) : score;
        scoreEl.className = `bias-score-value ${getBiasScoreClass(score)}`;
    }

    // Direction
    const directionEl = document.getElementById(`${prefix}BiasDirection`);
    if (directionEl) {
        directionEl.textContent = modelAnalysis.bias_direction || modelAnalysis.direction || 'Unknown';
    }

    // Justification - check multiple possible field names
    const justificationEl = document.getElementById(`${prefix}BiasJustification`);
    if (justificationEl) {
        const justification = modelAnalysis.summary || 
                             modelAnalysis.justification || 
                             modelAnalysis.reasoning ||
                             modelAnalysis.explanation ||
                             modelAnalysis.overall_assessment ||
                             '';
        justificationEl.textContent = justification;
    }

    // Details container
    const detailsEl = document.getElementById(`${prefix}BiasDetails`);
    if (detailsEl) {
        detailsEl.innerHTML = '';

        // Add bias indicators
        const indicators = modelAnalysis.bias_indicators || modelAnalysis.biases_detected || [];
        if (indicators.length > 0) {
            const indicatorsSection = createBiasSection('Bias Indicators', indicators);
            detailsEl.appendChild(indicatorsSection);
        }

        // Add language analysis
        if (modelAnalysis.language_analysis) {
            const langSection = createLanguageSection(modelAnalysis.language_analysis);
            detailsEl.appendChild(langSection);
        }

        // Add framing analysis
        if (modelAnalysis.framing_analysis) {
            const framingSection = createFramingSection(modelAnalysis.framing_analysis);
            detailsEl.appendChild(framingSection);
        }

        // Add balanced aspects if present
        if (modelAnalysis.balanced_aspects && modelAnalysis.balanced_aspects.length > 0) {
            const balancedSection = createBiasSection('Balanced Aspects', modelAnalysis.balanced_aspects);
            detailsEl.appendChild(balancedSection);
        }
    }
}

// ============================================
// DISPLAY CONSENSUS ANALYSIS
// ============================================

function displayConsensusAnalysis(consensus) {
    console.log('displayConsensusAnalysis:', consensus);

    // Score - check multiple possible field names
    const scoreEl = document.getElementById('consensusBiasScore');
    if (scoreEl) {
        const score = consensus.consensus_bias_score || 
                     consensus.average_score || 
                     consensus.score || 
                     0;
        scoreEl.textContent = score.toFixed ? score.toFixed(1) : score;
        scoreEl.className = `bias-score-value ${getBiasScoreClass(score)}`;
    }

    // Direction
    const directionEl = document.getElementById('consensusBiasDirection');
    if (directionEl) {
        directionEl.textContent = consensus.consensus_direction || consensus.direction || 'Unknown';
    }

    // Justification / Final Assessment
    const justificationEl = document.getElementById('consensusBiasJustification');
    if (justificationEl) {
        const justification = consensus.final_assessment || 
                             consensus.summary || 
                             consensus.justification ||
                             '';
        justificationEl.textContent = justification;
    }

    // Details
    const detailsEl = document.getElementById('consensusBiasDetails');
    if (detailsEl) {
        detailsEl.innerHTML = '';

        // Confidence indicator
        if (consensus.confidence) {
            const confidenceDiv = document.createElement('div');
            confidenceDiv.className = 'consensus-confidence';
            const confidencePercent = consensus.confidence > 1 ? consensus.confidence : Math.round(consensus.confidence * 100);
            confidenceDiv.innerHTML = `
                <span class="confidence-label">Confidence:</span>
                <span class="confidence-value">${confidencePercent}%</span>
            `;
            detailsEl.appendChild(confidenceDiv);
        }

        // Areas of agreement
        if (consensus.areas_of_agreement && consensus.areas_of_agreement.length > 0) {
            const agreementSection = createBiasSection('Areas of Agreement', consensus.areas_of_agreement);
            detailsEl.appendChild(agreementSection);
        }

        // Areas of disagreement
        if (consensus.areas_of_disagreement && consensus.areas_of_disagreement.length > 0) {
            const disagreementSection = createBiasSection('Areas of Disagreement', consensus.areas_of_disagreement);
            detailsEl.appendChild(disagreementSection);
        }

        // GPT unique findings
        if (consensus.gpt_unique_findings && consensus.gpt_unique_findings.length > 0) {
            const gptSection = createBiasSection('GPT Unique Findings', consensus.gpt_unique_findings);
            detailsEl.appendChild(gptSection);
        }

        // Claude unique findings
        if (consensus.claude_unique_findings && consensus.claude_unique_findings.length > 0) {
            const claudeSection = createBiasSection('Claude Unique Findings', consensus.claude_unique_findings);
            detailsEl.appendChild(claudeSection);
        }

        // Recommendations
        if (consensus.recommendations && consensus.recommendations.length > 0) {
            const recsSection = createBiasSection('Recommendations', consensus.recommendations);
            detailsEl.appendChild(recsSection);
        }
    }
}

// ============================================
// HELPER FUNCTIONS
// ============================================

function getBiasScoreClass(score) {
    const absScore = Math.abs(score);
    if (absScore <= 2) return 'score-low';
    if (absScore <= 5) return 'score-medium';
    return 'score-high';
}

function getAgreementClass(level) {
    if (!level) return 'agreement-low';
    switch (level.toLowerCase()) {
        case 'high':
        case 'strong':
            return 'agreement-high';
        case 'medium':
        case 'moderate':
            return 'agreement-medium';
        default:
            return 'agreement-low';
    }
}

function createBiasSection(title, items) {
    const section = document.createElement('div');
    section.className = 'bias-section';

    const itemsHtml = items.map(item => {
        if (typeof item === 'string') {
            return `<li>${escapeHtml(item)}</li>`;
        } else if (item.type && item.evidence) {
            // Format: { type: "Selection Bias", severity: 6, evidence: "..." }
            const severity = item.severity ? ` (${item.severity}/10)` : '';
            return `<li><strong>${escapeHtml(item.type)}</strong>${severity}: ${escapeHtml(item.evidence)}</li>`;
        } else if (item.description) {
            return `<li>${escapeHtml(item.description)}</li>`;
        } else if (item.text) {
            return `<li>${escapeHtml(item.text)}</li>`;
        } else {
            return `<li>${escapeHtml(JSON.stringify(item))}</li>`;
        }
    }).join('');

    section.innerHTML = `
        <h4 class="bias-section-title">${escapeHtml(title)}</h4>
        <ul class="bias-list">
            ${itemsHtml}
        </ul>
    `;

    return section;
}

function createLanguageSection(langAnalysis) {
    const section = document.createElement('div');
    section.className = 'bias-section';

    let content = '<h4 class="bias-section-title">Language Analysis</h4>';

    if (langAnalysis.loaded_terms && langAnalysis.loaded_terms.length > 0) {
        content += `
            <div class="lang-subsection">
                <span class="lang-label">Loaded Terms:</span>
                <span class="lang-value">${langAnalysis.loaded_terms.map(t => escapeHtml(t)).join(', ')}</span>
            </div>
        `;
    }

    if (langAnalysis.tone) {
        content += `
            <div class="lang-subsection">
                <span class="lang-label">Tone:</span>
                <span class="lang-value">${escapeHtml(langAnalysis.tone)}</span>
            </div>
        `;
    }

    if (langAnalysis.emotional_language) {
        content += `
            <div class="lang-subsection">
                <span class="lang-label">Emotional Language:</span>
                <span class="lang-value">${escapeHtml(langAnalysis.emotional_language)}</span>
            </div>
        `;
    }

    section.innerHTML = content;
    return section;
}

function createFramingSection(framingAnalysis) {
    const section = document.createElement('div');
    section.className = 'bias-section';

    let content = '<h4 class="bias-section-title">Framing Analysis</h4>';

    if (framingAnalysis.narrative_frame) {
        content += `
            <div class="framing-subsection">
                <span class="framing-label">Narrative Frame:</span>
                <span class="framing-value">${escapeHtml(framingAnalysis.narrative_frame)}</span>
            </div>
        `;
    }

    if (framingAnalysis.perspective) {
        content += `
            <div class="framing-subsection">
                <span class="framing-label">Perspective:</span>
                <span class="framing-value">${escapeHtml(framingAnalysis.perspective)}</span>
            </div>
        `;
    }

    if (framingAnalysis.omissions) {
        content += `
            <div class="framing-subsection">
                <span class="framing-label">Notable Omissions:</span>
                <span class="framing-value">${escapeHtml(framingAnalysis.omissions)}</span>
            </div>
        `;
    }

    section.innerHTML = content;
    return section;
}