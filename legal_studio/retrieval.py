"""Bounded Korean lexical retrieval and optional local Ollama vector reranking.
Scores rank the retrieved candidate set; they are not legal probability estimates.
"""
import math
import re
from collections import Counter
import httpx
from .llm import OllamaError


def tokens(text):
    words = re.findall(r'[가-힣A-Za-z0-9]+', text.casefold())
    result = []
    for word in words:
        result.append(word)
        if re.search('[가-힣]', word):
            result.extend(word[i:i+2] for i in range(len(word)-1))
    return result


def lexical_scores(query, documents):
    """BM25 with Korean character bigrams, no external tokenizer/model required."""
    counts = [Counter(tokens(text)) for text in documents]
    lengths = [sum(c.values()) for c in counts]
    avg = sum(lengths) / max(1, len(lengths)) or 1
    terms = set(tokens(query))
    scores = [0.0] * len(documents)
    for term in terms:
        df = sum(term in c for c in counts)
        idf = math.log(1 + (len(counts)-df+0.5)/(df+0.5))
        for i, count in enumerate(counts):
            tf = count[term]
            scores[i] += idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * lengths[i]/avg))
    return scores


def chunks(text, size=1800, overlap=180):
    return [(start, text[start:start+size]) for start in range(0, len(text), size-overlap)]


def select_context(question, corpus, budget=16000):
    """Find relevant windows across full text; keep source IDs and original wording.

    A newline separates windows: verification always uses the full original corpus.
    """
    if not corpus:
        return {}
    per_source = max(250, min(6000, budget//len(corpus)))
    result = {}
    for key, text in corpus.items():
        windows = chunks(text)
        scores = lexical_scores(question, [p[1] for p in windows])
        ranked = sorted(range(len(windows)), key=lambda i: (-scores[i], i))
        selected = []
        remaining = per_source
        for i in ranked:
            if remaining <= 0:
                break
            start, piece = windows[i]
            piece = piece[:remaining]
            selected.append((start, piece))
            remaining -= len(piece) + 1
        result[key] = '\n'.join(p for _, p in sorted(selected))
    return result


def cosine(a, b):
    if len(a) != len(b) or not a:
        raise OllamaError('임베딩 차원이 일치하지 않습니다.')
    norm = math.sqrt(sum(v*v for v in a) * sum(v*v for v in b))
    return sum(x*y for x,y in zip(a,b))/norm if norm else 0.0


class OllamaEmbedder:
    def __init__(self, base_url, model, transport=None):
        self.base_url, self.model, self.transport = base_url.rstrip('/'), model, transport

    def embed(self, texts):
        try:
            with httpx.Client(timeout=90, transport=self.transport) as client:
                response = client.post(self.base_url+'/api/embed', json={
                    'model':self.model, 'input':texts, 'truncate':False})
                response.raise_for_status()
                vectors = response.json()['embeddings']
            if len(vectors) != len(texts) or not vectors or not vectors[0]:
                raise ValueError('wrong vector count')
            dim = len(vectors[0])
            if any(len(v)!=dim or any(not isinstance(x,(float,int)) or not math.isfinite(x) for x in v) for v in vectors):
                raise ValueError('invalid vector')
            return vectors
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            raise OllamaError(f'임베딩 실패: {type(exc).__name__}; 키워드 순위로 대체') from exc


def rank_documents(query, texts, embedder=None):
    lexical = lexical_scores(query, texts)
    scores, method, warnings = lexical, 'BM25_KO_BIGRAM', []
    if embedder and texts:
        try:
            # Input length is bounded explicitly; no silent server truncation.
            selected = select_context(query, {str(i):t for i,t in enumerate(texts)}, budget=2400*len(texts))
            vectors = embedder.embed([query[:1500]] + [selected[str(i)][:2400] for i in range(len(texts))])
            semantic = [cosine(vectors[0],v) for v in vectors[1:]]
            lex_order = sorted(range(len(texts)), key=lambda i:(-lexical[i],i))
            sem_order = sorted(range(len(texts)), key=lambda i:(-semantic[i],i))
            # Reciprocal rank fusion avoids presenting incompatible scores as probabilities.
            scores = [1/(60+lex_order.index(i)+1) + 1/(60+sem_order.index(i)+1) for i in range(len(texts))]
            method = 'RRF_BM25_OLLAMA'
        except OllamaError as exc:
            warnings.append(str(exc))
    return scores, method, warnings


def counter_queries(query):
    base = query.strip()[:100]
    return [base+' 예외', base+' 부정', base+' 제한'] if base else []


def case_text(case):
    return '\n'.join([case.case_name,case.issues,case.summary,case.referenced_articles,case.referenced_cases,case.full_text])
