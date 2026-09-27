"""Policy stops retain evidence without becoming transport failures."""
import pytest
from fastapi.testclient import TestClient

from agent_audit_api.main import create_app
from agent_audit_api.providers.base import LLMResponse, ToolCall, ProviderUnavailableError
from tests.retriever_support import make_tfidf_retriever


class CustomerToolProvider:
    async def complete(self, messages, tools=None):
        return LLMResponse(content='', tool_calls=(
            ToolCall(id='denied-customer', name='mock_customer_lookup', arguments={'customerId': 'customer_002'}),
        ))


@pytest.mark.parametrize('path', [
    '/api/attack-cases/case_inside_out_customer_scope/execute',
    '/api/attack-plans/plan_resource_customer_owner/execute',
])
def test_policy_stop_retains_prior_resource_violation(path):
    app=create_app(provider=CustomerToolProvider(), retriever=make_tfidf_retriever())
    with TestClient(app) as client:
        response=client.post(path)
    assert response.status_code == 200
    result=response.json()
    assert result['executionStatus']=='blocked'
    assert result['queryResult'] is None
    events=result['traceEvents']
    assert events[-1]['details']['toolName']=='mock_customer_lookup'
    assert events[-1]['details']['decision']=='denied'
    assert not any(event['type']=='tool_result' for event in events)
    assert result['evaluation']['status']=='failed'
    assert 'resource_authorization_bypass' in {f['category'] for f in result['evaluation']['findings']}
    sequences={e['sequence'] for e in events}
    assert all(set(f['evidenceSequences']) <= sequences for f in result['evaluation']['findings'])


def test_secure_case_policy_stop_does_not_invent_a_violation():
    app=create_app(provider=CustomerToolProvider(), retriever=make_tfidf_retriever())
    app.state.attack_cases=tuple(case.model_copy(update={'target_profile_id':'secure'}) for case in app.state.attack_cases)
    with TestClient(app) as client:
        result=client.post('/api/attack-cases/case_inside_out_customer_scope/execute').json()
    assert result['executionStatus']=='blocked'
    assert result['evaluation']['status']=='passed'
    assert result['evaluation']['findings']==[]


def test_provider_failure_is_still_an_http_error():
    class UnavailableProvider:
        async def complete(self, messages, tools=None):
            raise ProviderUnavailableError('synthetic unavailable')
    with TestClient(create_app(provider=UnavailableProvider(), retriever=make_tfidf_retriever())) as client:
        response=client.post('/api/attack-cases/case_inside_out_customer_scope/execute')
    assert response.status_code == 502
