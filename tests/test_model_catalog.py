import httpx
from legal_studio.model_catalog import installed_models, choose_model


def test_capabilities_separate_chat_and_embedding_and_choose_installed_only():
    def handler(request):
        if request.url.path == '/api/tags':
            return httpx.Response(200, json={'models': [
                {'name':'large-local', 'size':30}, {'name':'small-local','size':10},
                {'name':'vectors-local','size':2}]})
        import json
        name=json.loads(request.content)['model']
        return httpx.Response(200,json={'capabilities':
            ['embedding'] if name=='vectors-local' else ['completion']})
    models=installed_models('http://localhost',httpx.MockTransport(handler))
    assert choose_model(models,'completion','missing-model')=='small-local'
    assert choose_model(models,'completion','large-local')=='large-local'
    assert choose_model(models,'embedding')=='vectors-local'
    assert choose_model([], 'embedding')==''
