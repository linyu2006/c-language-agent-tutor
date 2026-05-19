let currentController = null;

function submitAnalysis() {
    const code = document.getElementById('codeInput').value.trim();
    if (!code) {
        showError('请先输入 C 代码');
        return;
    }

    if (currentController) {
        currentController.abort();
    }
    currentController = new AbortController();

    const btn = document.getElementById('submitBtn');
    btn.disabled = true;
    btn.textContent = '分析中...';

    const container = document.getElementById('resultContainer');
    container.innerHTML = '';

    const formData = new FormData();
    formData.append('code', code);
    formData.append('problem', document.getElementById('problemInput').value.trim());
    formData.append('test_inputs', document.getElementById('testInputs').value);
    formData.append('test_outputs', document.getElementById('testOutputs').value);

    const state = {
        analysisReport: null,
        tutoringResult: null,
        verificationResult: null,
        finalCode: null,
    };

    fetch('/analyze', {
        method: 'POST',
        body: formData,
        signal: currentController.signal,
    }).then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return readSSEStream(response, state);
    }).catch(err => {
        if (err.name !== 'AbortError') {
            showError(err.message || '请求失败');
        }
    }).finally(() => {
        btn.disabled = false;
        btn.textContent = '提交分析';
        currentController = null;
    });
}

async function readSSEStream(response, state) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
            if (line.startsWith('data: ')) {
                const data = line.slice(6);
                if (data === '[DONE]') return;
                try {
                    const event = JSON.parse(data);
                    handleEvent(event, state);
                } catch (e) {
                    // skip malformed JSON
                }
            }
        }
    }
}

function handleEvent(event, state) {
    const container = document.getElementById('resultContainer');
    const agent = event.agent;
    const stage = event.stage;

    if (stage === 'error') {
        showError(event.message);
        return;
    }

    if (stage === 'start') {
        addProgressCard(container, agent, event.message);
        return;
    }

    if (stage === 'done' && event.data) {
        const data = event.data;
        if (agent === 'understanding') {
            state.analysisReport = data;
            renderAnalysisReport(container, data);
        } else if (agent === 'tutoring') {
            state.tutoringResult = data;
            renderTutoringResult(container, data);
        } else if (agent === 'verification') {
            state.verificationResult = data;
            renderVerificationResult(container, data);
        } else if (agent === 'orchestrator') {
            renderFinalSummary(container, data, event.message);
        }
        return;
    }

    if (stage === 'retry') {
        addRetryCard(container, event);
        return;
    }

    if (stage === 'analyzing' || stage === 'tutoring') {
        updateStreamingCard(container, agent, event);
        return;
    }

    if (stage === 'verifying') {
        addProgressCard(container, agent, event.message);
    }
}

function addProgressCard(container, agent, message) {
    const card = document.createElement('div');
    card.className = `agent-event agent-${agent}`;
    card.innerHTML = `<div class="event-header"><span class="spinner"></span>${escapeHtml(message)}</div>`;
    container.appendChild(card);
    container.scrollTop = container.scrollHeight;
}

function addRetryCard(container, event) {
    const card = document.createElement('div');
    card.className = 'agent-event agent-orchestrator';
    card.innerHTML = `
        <div class="event-header">&#8635; 闭环反馈：第 ${event.round || '?'} 轮重试</div>
        <div class="event-body">${escapeHtml(event.message)}</div>
    `;
    container.appendChild(card);
    container.scrollTop = container.scrollHeight;
}

function updateStreamingCard(container, agent, event) {
    let card = container.querySelector(`.agent-${agent}.streaming`);
    if (!card) {
        card = document.createElement('div');
        card.className = `agent-event agent-${agent} streaming`;
        card.innerHTML = `<div class="event-header">${agentLabel(agent)} 思考中...</div><div class="event-body stream-content"></div>`;
        container.appendChild(card);
    }
    const body = card.querySelector('.stream-content');
    if (body && event.chunk) {
        body.textContent += event.chunk;
    }
    container.scrollTop = container.scrollHeight;
}

function renderAnalysisReport(container, data) {
    removeStreamingCards(container);

    const errors = data.errors || [];
    const gcc = data.gcc_result || {};
    const summary = data.summary || '';

    let html = '<div class="agent-event agent-understanding"><div class="event-header">&#128270; 理解 Agent - 分析完成</div><div class="event-body">';

    if (summary) {
        html += `<div class="summary-box">${escapeHtml(summary)}</div>`;
    }

    if (gcc.raw_output) {
        html += `<details style="margin:8px 0"><summary style="cursor:pointer;font-size:13px;color:#666">GCC 编译器原始输出</summary><pre style="background:#f6f8fa;padding:8px;font-size:11px;overflow-x:auto;margin-top:6px;border-radius:4px">${escapeHtml(gcc.raw_output)}</pre></details>`;
    }

    errors.forEach((e, i) => {
        html += `
            <div class="error-item">
                <div style="margin-bottom:4px">
                    <span class="error-type-tag">${escapeHtml(e.type || 'unknown')}</span>
                    ${e.severity ? `<span class="severity-tag ${e.severity}">${escapeHtml(e.severity)}</span>` : ''}
                    ${e.line ? `<span style="font-size:11px;color:#888">行 ${e.line}</span>` : ''}
                </div>
                <strong>${escapeHtml(e.title || '')}</strong>
                <p style="margin:4px 0;color:#555">${escapeHtml(e.description || '')}</p>
                ${e.code_snippet ? `<code class="before-code-block">${escapeHtml(e.code_snippet)}</code>` : ''}
                ${e.root_cause ? `<p style="font-size:12px;color:#888;margin-top:4px">根因: ${escapeHtml(e.root_cause)}</p>` : ''}
            </div>`;
    });

    if (errors.length === 0) {
        html += '<p style="color:#27ae60">未发现代码问题。</p>';
    }

    html += '</div></div>';
    container.insertAdjacentHTML('beforeend', html);
    container.scrollTop = container.scrollHeight;
}

function renderTutoringResult(container, data) {
    removeStreamingCards(container);

    const explanations = data.explanations || [];
    const weakPoints = data.weak_points || [];
    const correctedCode = data.corrected_full_code || '';
    const encouragement = data.encouragement || '';

    let html = '<div class="agent-event agent-tutoring"><div class="event-header">&#128214; 辅导 Agent - 辅导建议</div><div class="event-body">';

    if (encouragement) {
        html += `<div class="encouragement">${escapeHtml(encouragement)}</div>`;
    }

    explanations.forEach(exp => {
        html += `
            <div class="tutor-item">
                <div style="margin-bottom:4px">
                    <span class="concept-badge">${escapeHtml(exp.concept || 'C 语言基础')}</span>
                </div>
                <p><strong>为什么错？</strong>${escapeHtml(exp.why_wrong || '')}</p>
                ${exp.analogy ? `<p style="color:#666;margin:4px 0"><strong>打个比方：</strong>${escapeHtml(exp.analogy)}</p>` : ''}
                <p style="margin:4px 0"><strong>怎么改？</strong>${escapeHtml(exp.fix_guide || '')}</p>
                ${exp.before_code ? `<div style="font-size:11px;color:#888;margin-top:6px">修改前:</div><code class="before-code-block">${escapeHtml(exp.before_code)}</code>` : ''}
                ${exp.after_code ? `<div style="font-size:11px;color:#888;margin-top:6px">修改后:</div><code class="corrected-code-block">${escapeHtml(exp.after_code)}</code>` : ''}
                ${exp.study_tip ? `<p style="font-size:12px;color:#4a90d9;margin-top:6px">学习建议: ${escapeHtml(exp.study_tip)}</p>` : ''}
            </div>`;
    });

    if (weakPoints.length > 0) {
        html += '<div style="margin-top:12px"><strong>薄弱知识点：</strong>';
        weakPoints.forEach(wp => {
            html += `<span class="weak-point-badge">${escapeHtml(wp)}</span> `;
        });
        html += '</div>';
    }

    if (correctedCode) {
        html += `<details style="margin-top:12px"><summary style="cursor:pointer;font-size:13px;color:#4a90d9;font-weight:500">查看完整修正代码</summary><pre class="corrected-code-block" style="margin-top:8px">${escapeHtml(correctedCode)}</pre></details>`;
    }

    html += '</div></div>';
    container.insertAdjacentHTML('beforeend', html);
    container.scrollTop = container.scrollHeight;
}

function renderVerificationResult(container, data) {
    removeStreamingCards(container);

    const compilationOk = data.compilation_ok;
    const testSummary = data.test_summary || {};
    const testDetails = data.test_details || [];
    const failureAnalysis = data.failure_analysis || '';

    let icon = '&#10060;';
    if (compilationOk && testSummary.failed === 0) {
        icon = '&#9989;';
    } else if (compilationOk) {
        icon = '&#9888;';
    }

    let html = `<div class="agent-event agent-verification"><div class="event-header">${icon} 验证 Agent - 验证结果</div><div class="event-body">`;

    if (!compilationOk) {
        html += `<p style="color:#e74c3c"><strong>编译失败</strong></p>`;
        if (data.compile_errors) {
            html += `<pre style="background:#fff5f5;padding:8px;font-size:12px;border-radius:4px;overflow-x:auto">${escapeHtml(data.compile_errors)}</pre>`;
        }
    } else {
        html += `<p style="color:#27ae60"><strong>编译成功</strong></p>`;
    }

    if (testDetails.length > 0) {
        html += `<div style="margin:8px 0"><strong>测试结果: ${testSummary.passed || 0}/${testSummary.total || 0} 通过</strong></div>`;
        testDetails.forEach(t => {
            const passClass = t.passed ? 'test-pass' : 'test-fail';
            const passIcon = t.passed ? '&#10004;' : '&#10008;';
            html += `<div class="test-row"><span class="${passClass}">${passIcon}</span> 输入: <code>${escapeHtml(t.input || '(空)')}</code> 期望: <code>${escapeHtml(t.expected_output || '')}</code> 实际: <code>${escapeHtml(t.actual_output || '')}</code></div>`;
        });
    }

    if (failureAnalysis && !data.all_passed) {
        html += `<p style="margin-top:8px;color:#e74c3c;font-size:13px"><strong>失败分析：</strong>${escapeHtml(failureAnalysis)}</p>`;
    }

    html += '</div></div>';
    container.insertAdjacentHTML('beforeend', html);
    container.scrollTop = container.scrollHeight;
}

function renderFinalSummary(container, data, message) {
    const rounds = data.rounds || 1;
    const maxRoundsReached = data.max_rounds_reached || false;

    let html = '<div class="agent-event agent-orchestrator"><div class="event-header">&#127919; 分析完成</div><div class="event-body">';

    if (maxRoundsReached) {
        html += '<p style="color:#d68910">达到最大重试次数，以下是当前最佳结果。</p>';
    } else {
        html += `<p style="color:#27ae60">${escapeHtml(message || '所有测试通过！')}</p>`;
    }

    html += `<p style="font-size:12px;color:#888;margin-top:4px">共执行 ${rounds} 轮辅导-验证循环</p>`;
    html += '</div></div>';
    container.insertAdjacentHTML('beforeend', html);
    container.scrollTop = container.scrollHeight;
}

function showError(message) {
    const container = document.getElementById('resultContainer');
    const el = document.createElement('div');
    el.className = 'agent-event agent-system';
    el.innerHTML = `<div class="event-header">&#10060; 错误</div><div class="event-body">${escapeHtml(message)}</div>`;
    container.appendChild(el);
    container.scrollTop = container.scrollHeight;
}

function removeStreamingCards(container) {
    container.querySelectorAll('.streaming').forEach(el => el.remove());
}

function agentLabel(agent) {
    const labels = { understanding: '理解 Agent', tutoring: '辅导 Agent', verification: '验证 Agent' };
    return labels[agent] || agent;
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function clearAll() {
    document.getElementById('codeInput').value = '';
    document.getElementById('problemInput').value = '';
    document.getElementById('testInputs').value = '';
    document.getElementById('testOutputs').value = '';
    document.getElementById('resultContainer').innerHTML = `
        <div class="placeholder">
            <div class="placeholder-icon">&#9000;</div>
            <p>提交代码后将在此处显示三个 Agent 的协作分析过程</p>
            <div class="agent-flow">
                <span class="flow-step">理解 Agent</span>
                <span class="flow-arrow">&rarr;</span>
                <span class="flow-step">辅导 Agent</span>
                <span class="flow-arrow">&rarr;</span>
                <span class="flow-step">验证 Agent</span>
                <span class="flow-arrow">&rarr;</span>
                <span class="flow-step">闭环反馈</span>
            </div>
        </div>`;
    if (currentController) {
        currentController.abort();
        currentController = null;
    }
    const btn = document.getElementById('submitBtn');
    btn.disabled = false;
    btn.textContent = '提交分析';
}
