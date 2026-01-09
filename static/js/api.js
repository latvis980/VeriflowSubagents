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
        addProgress('🔍 Starting LLM interpretation verification...');

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
        addProgress('🔍 Starting web search fact-checking...');

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

            addProgress(`📰 Source: ${sourceContext.publication} | Tier ${sourceContext.credibility_tier} | ${sourceContext.bias_rating || 'Unknown bias'}`);
        }

        const response = await fetch('/api/check', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: content,
                input_type: 'text',
                // NEW: Pass source context
                source_context: sourceContext
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
        addProgress('🎯 Extracting and verifying key claims...');

        // Get metadata from fetched article for context
        const fetchedArticle = getLastFetchedArticle();
        let sourceContext = null;

        if (fetchedArticle) {
            sourceContext = {
                publication: fetchedArticle.publication_name || fetchedArticle.domain,
                author: fetchedArticle.author,
                date: fetchedArticle.publication_date,
                credibility: fetchedArticle.credibility
            };

            if (sourceContext.credibility) {
                const tier = sourceContext.credibility.tier;
                const tierDescriptions = {
                    1: 'highly credible',
                    2: 'credible',
                    3: 'mixed credibility',
                    4: 'low credibility',
                    5: 'unreliable'
                };
                addProgress(`📰 Source: ${sourceContext.publication} (${tierDescriptions[tier] || 'unknown'})`);
            }
        }

        const response = await fetch('/api/key-claims', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: content,
                // NEW: Pass source context for claim verification
                source_context: sourceContext
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Key claims check failed');
        }

        const data = await response.json();
        AppState.currentJobIds.keyClaims = data.job_id;

        await streamKeyClaimsProgress(data.job_id);

    } catch (error) {
        console.error('Key claims check error:', error);
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

async function runBiasCheck(content) {
    try {
        addProgress('📊 Starting bias analysis...');

        // Get publication URL from input field
        let pubUrl = publicationUrl?.value?.trim() || null;

        // If we fetched an article, use its credibility data
        const fetchedArticle = getLastFetchedArticle();
        let sourceCredibility = null;

        if (fetchedArticle) {
            // Use the domain from fetched article if no manual URL provided
            if (!pubUrl && fetchedArticle.domain) {
                pubUrl = `https://${fetchedArticle.domain}`;
            }

            // Pass along the credibility we already have
            if (fetchedArticle.credibility) {
                sourceCredibility = fetchedArticle.credibility;
                addProgress(`📰 Using credibility data: Tier ${sourceCredibility.tier} - ${sourceCredibility.bias_rating || 'Unknown bias'}`);
            }
        }

        const response = await fetch('/api/check-bias', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                text: content,
                publication_url: pubUrl,
                // NEW: Pass pre-fetched credibility to avoid duplicate lookups
                source_credibility: sourceCredibility
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

        // Get metadata from fetched article
        const fetchedArticle = getLastFetchedArticle();
        let articleSource = null;
        let articleDate = null;
        let sourceCredibility = null;

        if (fetchedArticle) {
            articleSource = fetchedArticle.publication_name || fetchedArticle.domain;
            articleDate = fetchedArticle.publication_date;
            sourceCredibility = fetchedArticle.credibility;

            if (articleSource) {
                addProgress(`📰 Analyzing article from: ${articleSource}`);
            }
            if (sourceCredibility) {
                addProgress(`🔍 Source credibility: Tier ${sourceCredibility.tier}`);
            }
        }

        const response = await fetch('/api/check-lie-detection', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                text: content,
                article_source: articleSource,
                article_date: articleDate,
                // NEW: Pass credibility for context
                source_credibility: sourceCredibility
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

// ============================================
// MANIPULATION DETECTION
// ============================================

async function runManipulationCheck(content) {
    try {
        addProgress('🎭 Analyzing for manipulation techniques...');

        // Get metadata from fetched article
        const fetchedArticle = getLastFetchedArticle();
        let sourceInfo = 'Unknown source';
        let sourceCredibility = null;

        if (fetchedArticle) {
            const parts = [];
            if (fetchedArticle.publication_name) parts.push(fetchedArticle.publication_name);
            else if (fetchedArticle.domain) parts.push(fetchedArticle.domain);
            if (fetchedArticle.author) parts.push(`by ${fetchedArticle.author}`);
            if (fetchedArticle.publication_date) parts.push(`(${fetchedArticle.publication_date})`);

            if (parts.length > 0) {
                sourceInfo = parts.join(' ');
            }

            sourceCredibility = fetchedArticle.credibility;

            if (sourceCredibility) {
                addProgress(`🔍 Source credibility: Tier ${sourceCredibility.tier} - ${sourceCredibility.factual_reporting || 'Unknown'} factual reporting`);
            }
        }

        const response = await fetch('/api/manipulation', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: content,
                source_info: sourceInfo,
                // NEW: Pass credibility for enhanced analysis
                source_credibility: sourceCredibility
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Manipulation check failed');
        }

        const data = await response.json();
        AppState.currentJobIds.manipulation = data.job_id;

        await streamManipulationProgress(data.job_id);

    } catch (error) {
        console.error('Manipulation check error:', error);
        addProgress(`❌ Manipulation analysis failed: ${error.message}`, 'error');
        throw error;
    }
}


async function streamManipulationProgress(jobId) {
    const result = await streamJobProgress(jobId, '🎭');
    AppState.currentManipulationResults = result;
    console.log('Manipulation analysis completed:', result);
    addProgress('✅ Manipulation analysis completed');
    return result;
}