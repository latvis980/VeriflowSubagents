// static/js/api.js - API Calls and Streaming
// VeriFlow Redesign - Minimalist Theme

// ============================================
// UNIFIED STREAMING WITH AUTO-RECONNECTION
// ============================================

function streamJobProgress(jobId, emoji = '•', reconnectAttempts = 0) {
    const maxReconnects = 3;
    const baseDelay = 2000;

    return new Promise((resolve, reject) => {
        const eventSource = new EventSource(`/api/job/${jobId}/stream`);
        AppState.activeEventSources.push(eventSource);

        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);

            // Ignore heartbeats
            if (data.heartbeat) {
                return;
            }

            // Handle completion
            if (data.status === 'completed') {
                addProgress('Analysis complete');
                eventSource.close();
                resolve(data.result);
                return;
            }

            // Handle failure
            if (data.status === 'failed') {
                addProgress(`Failed: ${data.error || 'Unknown error'}`, 'error');
                eventSource.close();
                reject(new Error(data.error || 'Job failed'));
                return;
            }

            // Handle cancellation
            if (data.status === 'cancelled') {
                addProgress('Job cancelled');
                eventSource.close();
                reject(new Error('Job cancelled by user'));
                return;
            }

            // Handle progress messages
            if (data.message) {
                addProgress(data.message);
            }

            // Handle status updates without message
            if (data.status && !data.message) {
                addProgress(`${data.status}`);
            }
        };

        eventSource.onerror = (error) => {
            console.error('EventSource error:', error);
            eventSource.close();

            // Attempt reconnection
            if (reconnectAttempts < maxReconnects) {
                const delay = baseDelay * Math.pow(2, reconnectAttempts);
                console.log(`Reconnecting in ${delay/1000}s... (Attempt ${reconnectAttempts + 1}/${maxReconnects})`);
                addProgress(`Connection lost. Reconnecting...`);

                setTimeout(() => {
                    streamJobProgress(jobId, emoji, reconnectAttempts + 1)
                        .then(resolve)
                        .catch(reject);
                }, delay);
            } else {
                addProgress('Connection failed after multiple attempts', 'error');
                reject(new Error('Stream connection failed after retries'));
            }
        };
    });
}

// ============================================
// URL FETCHING (JOB-BASED - uses /api/scrape-url)
// ============================================

async function fetchArticleFromUrl(url, options = {}) {
    const {
        extractMetadata = true,
        checkCredibility = true,
        runMbfcIfMissing = true
    } = options;

    try {
        // Step 1: Start the scrape job
        const startResponse = await fetch('/api/scrape-url', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                url: url,
                extract_metadata: extractMetadata,
                check_credibility: checkCredibility,
                run_mbfc_if_missing: runMbfcIfMissing
            })
        });

        if (!startResponse.ok) {
            const error = await startResponse.json();
            throw new Error(error.error || 'Failed to start URL fetch');
        }

        const startData = await startResponse.json();
        const jobId = startData.job_id;

        if (!jobId) {
            throw new Error('No job ID returned from server');
        }

        // Step 2: Poll for job completion
        const result = await pollJobCompletion(jobId, 60000, 1000);
        
        // Store for later use
        setLastFetchedArticle(result);
        
        return result;

    } catch (error) {
        console.error('URL fetch error:', error);
        throw error;
    }
}

/**
 * Poll job status until completion
 */
async function pollJobCompletion(jobId, timeout = 60000, pollInterval = 1000) {
    const startTime = Date.now();

    while (Date.now() - startTime < timeout) {
        try {
            const response = await fetch(`/api/job/${jobId}`);
            
            if (!response.ok) {
                throw new Error('Job not found');
            }

            const job = await response.json();

            if (job.status === 'completed') {
                return job.result;
            }

            if (job.status === 'failed') {
                throw new Error(job.error || 'Job failed');
            }

            if (job.status === 'cancelled') {
                throw new Error('Job was cancelled');
            }

            // Wait before next poll
            await new Promise(resolve => setTimeout(resolve, pollInterval));

        } catch (error) {
            if (error.message.includes('Job not found')) {
                throw new Error('Job expired or not found');
            }
            throw error;
        }
    }

    throw new Error('Timeout waiting for job completion');
}

// ============================================
// LLM VERIFICATION
// ============================================

async function runLLMVerification(content) {
    try {
        addProgress('Starting LLM interpretation verification...');

        // Get source context if available
        const fetchedArticle = getLastFetchedArticle();
        let sourceContext = null;

        if (fetchedArticle && fetchedArticle.credibility) {
            sourceContext = {
                publication: fetchedArticle.publication_name || fetchedArticle.domain,
                credibility_tier: fetchedArticle.credibility.tier,
                bias_rating: fetchedArticle.credibility.bias_rating
            };
        }

        const response = await fetch('/api/check', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: content,
                input_type: 'html',
                source_context: sourceContext
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'LLM verification failed');
        }

        const data = await response.json();
        AppState.currentJobIds.llmVerification = data.job_id;

        const result = await streamJobProgress(data.job_id, '•');
        AppState.currentLLMVerificationResults = result;
        addProgress('LLM interpretation verification completed');
        return result;

    } catch (error) {
        console.error('LLM verification error:', error);
        addProgress(`LLM verification failed: ${error.message}`, 'error');
        throw error;
    }
}

// ============================================
// FACT CHECKING (Web Search)
// ============================================

async function runFactCheck(content) {
    try {
        addProgress('Starting web search fact-checking...');

        // Get source context if available
        const fetchedArticle = getLastFetchedArticle();
        let sourceContext = null;

        if (fetchedArticle && fetchedArticle.credibility) {
            sourceContext = {
                publication: fetchedArticle.publication_name || fetchedArticle.domain,
                credibility_tier: fetchedArticle.credibility.tier,
                bias_rating: fetchedArticle.credibility.bias_rating,
                factual_reporting: fetchedArticle.credibility.factual_reporting
            };
            addProgress(`Source: ${sourceContext.publication} | Tier ${sourceContext.credibility_tier}`);
        }

        const response = await fetch('/api/check', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: content,
                input_type: 'text',
                source_context: sourceContext
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Fact check failed');
        }

        const data = await response.json();
        AppState.currentJobIds.factCheck = data.job_id;

        const result = await streamJobProgress(data.job_id, '•');
        AppState.currentFactCheckResults = result;
        addProgress('Fact checking completed');
        return result;

    } catch (error) {
        console.error('Fact check error:', error);
        addProgress(`Fact check failed: ${error.message}`, 'error');
        throw error;
    }
}

// ============================================
// KEY CLAIMS CHECKING
// ============================================

async function runKeyClaimsCheck(content) {
    try {
        addProgress('Starting key claims analysis...');

        // Get source context if available
        const fetchedArticle = getLastFetchedArticle();
        let sourceContext = null;

        if (fetchedArticle && fetchedArticle.credibility) {
            sourceContext = {
                publication: fetchedArticle.publication_name || fetchedArticle.domain,
                credibility_tier: fetchedArticle.credibility.tier,
                bias_rating: fetchedArticle.credibility.bias_rating
            };
        }

        const response = await fetch('/api/key-claims', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: content,
                source_context: sourceContext
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Key claims check failed');
        }

        const data = await response.json();
        AppState.currentJobIds.keyClaims = data.job_id;

        const result = await streamJobProgress(data.job_id, '•');
        AppState.currentKeyClaimsResults = result;
        addProgress('Key claims analysis completed');
        return result;

    } catch (error) {
        console.error('Key claims error:', error);
        addProgress(`Key claims analysis failed: ${error.message}`, 'error');
        throw error;
    }
}

// ============================================
// BIAS ANALYSIS
// ============================================

async function runBiasCheck(content) {
    try {
        addProgress('Starting bias analysis...');

        // Get source context if available
        const fetchedArticle = getLastFetchedArticle();
        let sourceContext = null;

        if (fetchedArticle && fetchedArticle.credibility) {
            sourceContext = {
                publication: fetchedArticle.publication_name || fetchedArticle.domain,
                credibility_tier: fetchedArticle.credibility.tier,
                bias_rating: fetchedArticle.credibility.bias_rating
            };
        }

        const response = await fetch('/api/bias', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: content,
                source_context: sourceContext
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Bias check failed');
        }

        const data = await response.json();
        AppState.currentJobIds.biasCheck = data.job_id;

        const result = await streamJobProgress(data.job_id, '•');
        AppState.currentBiasResults = result;
        addProgress('Bias analysis completed');
        return result;

    } catch (error) {
        console.error('Bias check error:', error);
        addProgress(`Bias analysis failed: ${error.message}`, 'error');
        throw error;
    }
}

// ============================================
// LIE DETECTION
// ============================================

async function runLieDetection(content) {
    try {
        addProgress('Starting deception detection...');

        const response = await fetch('/api/lie-detection', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ content: content })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Lie detection failed');
        }

        const data = await response.json();
        AppState.currentJobIds.lieDetection = data.job_id;

        const result = await streamJobProgress(data.job_id, '•');
        AppState.currentLieDetectionResults = result;
        addProgress('Deception detection completed');
        return result;

    } catch (error) {
        console.error('Lie detection error:', error);
        addProgress(`Deception detection failed: ${error.message}`, 'error');
        throw error;
    }
}

// ============================================
// MANIPULATION CHECK
// ============================================

async function runManipulationCheck(content) {
    try {
        addProgress('Starting manipulation analysis...');

        // Get source context if available
        const fetchedArticle = getLastFetchedArticle();
        let sourceContext = null;

        if (fetchedArticle && fetchedArticle.credibility) {
            sourceContext = {
                publication: fetchedArticle.publication_name || fetchedArticle.domain,
                credibility_tier: fetchedArticle.credibility.tier,
                bias_rating: fetchedArticle.credibility.bias_rating
            };
        }

        const response = await fetch('/api/manipulation', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: content,
                source_context: sourceContext
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Manipulation check failed');
        }

        const data = await response.json();
        AppState.currentJobIds.manipulation = data.job_id;

        const result = await streamJobProgress(data.job_id, '•');
        AppState.currentManipulationResults = result;
        addProgress('Manipulation analysis completed');
        return result;

    } catch (error) {
        console.error('Manipulation check error:', error);
        addProgress(`Manipulation analysis failed: ${error.message}`, 'error');
        throw error;
    }
}
