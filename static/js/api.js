// static/js/api.js - API Calls and Streaming

// ============================================
// UNIFIED STREAMING WITH AUTO-RECONNECTION
// ============================================

function streamJobProgress(jobId, emoji = '⏳', reconnectAttempts = 0) {
    const maxReconnects = 3;
    const baseDelay = 2000;

    return new Promise((resolve, reject) => {
        const eventSource = new EventSource(`/api/job/${jobId}/stream`);
        AppState.activeEventSources.push(eventSource);

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.heartbeat) {
                return;
            }

            if (data.status === 'completed') {
                addProgress(`${emoji} Complete!`);
                eventSource.close();
                resolve(data.result);
                return;
            }

            if (data.status === 'failed') {
                addProgress(`${emoji} Failed: ${data.error || 'Unknown error'}`, 'error');
                eventSource.close();
                reject(new Error(data.error || 'Job failed'));
                return;
            }

            if (data.status === 'cancelled') {
                addProgress(`${emoji} Job cancelled`);
                eventSource.close();
                reject(new Error('Job cancelled by user'));
                return;
            }

            if (data.message) {
                addProgress(data.message);
            }

            if (data.status && !data.message) {
                addProgress(`🔄 ${data.status}`);
            }
        };

        eventSource.onerror = (error) => {
            console.error('EventSource error:', error);
            eventSource.close();

            if (reconnectAttempts < maxReconnects) {
                const delay = baseDelay * Math.pow(2, reconnectAttempts);
                console.log(`Connection lost. Reconnecting in ${delay/1000}s... (Attempt ${reconnectAttempts + 1}/${maxReconnects})`);
                addProgress(`⚠️ Connection lost. Reconnecting in ${delay/1000}s...`);

                setTimeout(() => {
                    console.log(`Reconnecting to job ${jobId}...`);
                    streamJobProgress(jobId, emoji, reconnectAttempts + 1)
                        .then(resolve)
                        .catch(reject);
                }, delay);
            } else {
                addProgress(`❌ Connection failed after ${maxReconnects} attempts`, 'error');
                reject(new Error('Stream connection failed after retries'));
            }
        };
    });
}

// ============================================
// LLM VERIFICATION
// ============================================

async function runLLMVerification(content) {
    try {
        const response = await fetch('/api/check', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: content,
                input_type: 'html'
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'LLM verification failed');
        }

        const data = await response.json();
        AppState.currentJobIds.llmVerification = data.job_id;

        await streamLLMVerificationProgress(data.job_id);

    } catch (error) {
        console.error('LLM verification error:', error);
        addProgress(`❌ LLM verification failed: ${error.message}`, 'error');
        throw error;
    }
}

async function streamLLMVerificationProgress(jobId) {
    const result = await streamJobProgress(jobId, '🔍');
    AppState.currentLLMVerificationResults = result;
    console.log('LLM Verification completed:', result);
    addProgress('✅ LLM interpretation verification completed');
    return result;
}

// ============================================
// FACT CHECKING (Web Search Only)
// ============================================

async function runFactCheck(content) {
    try {
        const response = await fetch('/api/check', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: content,
                input_type: 'text'
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Fact check failed');
        }

        const data = await response.json();
        AppState.currentJobIds.factCheck = data.job_id;

        await streamFactCheckProgress(data.job_id);

    } catch (error) {
        console.error('Fact check error:', error);
        addProgress(`❌ Fact check failed: ${error.message}`, 'error');
        throw error;
    }
}

async function streamFactCheckProgress(jobId) {
    const result = await streamJobProgress(jobId, '🔎');
    AppState.currentFactCheckResults = result;
    console.log('Fact check completed:', result);
    addProgress('✅ Fact checking completed');
    return result;
}

// ============================================
// KEY CLAIMS CHECKING
// ============================================

async function runKeyClaimsCheck(content) {
    try {
        const response = await fetch('/api/key-claims', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: content
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Key claims analysis failed');
        }

        const data = await response.json();
        AppState.currentJobIds.keyClaims = data.job_id;

        await streamKeyClaimsProgress(data.job_id);

    } catch (error) {
        console.error('Key claims error:', error);
        addProgress(`❌ Key claims analysis failed: ${error.message}`, 'error');
        throw error;
    }
}

async function streamKeyClaimsProgress(jobId) {
    const result = await streamJobProgress(jobId, '🎯');
    AppState.currentKeyClaimsResults = result;
    console.log('Key claims analysis completed:', result);
    addProgress('✅ Key claims analysis completed');
    return result;
}

// ============================================
// BIAS ANALYSIS
// ============================================

// ============================================
// BIAS ANALYSIS
// ============================================

async function runBiasCheck(content) {
    try {
        addProgress('📊 Starting bias analysis...');

        // NEW: Get publication URL instead of name
        const pubUrl = publicationUrl.value.trim() || null;

        // Log if we have a URL to look up
        if (pubUrl) {
            addProgress(`📰 Will look up bias data for: ${pubUrl}`);
        }

        const response = await fetch('/api/check-bias', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                text: content,
                publication_url: pubUrl  // CHANGED: was publication_name
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Bias check failed');
        }

        const data = await response.json();
        AppState.currentJobIds.biasCheck = data.job_id;

        await streamBiasProgress(data.job_id);

    } catch (error) {
        console.error('Bias check error:', error);
        addProgress(`❌ Bias analysis failed: ${error.message}`, 'error');
        throw error;
    }
}

async function streamBiasProgress(jobId) {
    const result = await streamJobProgress(jobId, '📊');
    AppState.currentBiasResults = result;
    addProgress('✅ Bias analysis completed');
    return result;
}

async function streamBiasProgress(jobId) {
    const result = await streamJobProgress(jobId, '📊');
    AppState.currentBiasResults = result;
    addProgress('✅ Bias analysis completed');
    return result;
}

// ============================================
// LIE DETECTION
// ============================================

async function runLieDetection(content) {
    try {
        addProgress('🕵️ Analyzing text for deception markers...');

        const response = await fetch('/api/check-lie-detection', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                text: content
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Lie detection failed');
        }

        const data = await response.json();
        AppState.currentJobIds.lieDetection = data.job_id;

        await streamLieDetectionProgress(data.job_id);

    } catch (error) {
        console.error('Lie detection error:', error);
        addProgress(`❌ Lie detection failed: ${error.message}`, 'error');
        throw error;
    }
}

async function streamLieDetectionProgress(jobId) {
    const result = await streamJobProgress(jobId, '🕵️');
    AppState.currentLieDetectionResults = result;
    addProgress('✅ Lie detection analysis completed');
    return result;
}
