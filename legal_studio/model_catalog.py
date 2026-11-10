"""Discover installed models by server capabilities, never by model name."""
import httpx


def installed_models(base_url, transport=None):
    try:
        with httpx.Client(timeout=5, transport=transport) as client:
            response = client.get(base_url.rstrip('/') + '/api/tags')
            response.raise_for_status()
            models = []
            for item in response.json().get('models', []):
                name = item.get('name')
                if not name:
                    continue
                info = client.post(base_url.rstrip('/') + '/api/show', json={'model': name})
                info.raise_for_status()
                models.append({'name': name, 'size': item.get('size', 0),
                               'capabilities': info.json().get('capabilities', [])})
            return sorted(models, key=lambda m: (m['size'], m['name']))
    except (httpx.HTTPError, ValueError, TypeError):
        return []


def choose_model(models, capability, preferred=''):
    names = [m['name'] for m in models if capability in m['capabilities']]
    return preferred if preferred in names else (names[0] if names else '')
