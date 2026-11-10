"""Run: python -m legal_studio.doctor [--live]. Never prints credential values."""
import argparse
import json
import platform
import sqlite3
from .config import Settings
from .sources import LawOpenAPI, SourceError
from .llm import OllamaResearcher
from .model_catalog import installed_models, choose_model
from .retrieval import OllamaEmbedder
from .browser_tasks import ego_status


def diagnose(live=False):
    cfg=Settings.from_env()
    # SQLite FTS5 availability is a compile option; probing it in a temporary
    # database can leave Windows file handles locked. Check the runtime directly.
    probe=sqlite3.connect(':memory:')
    try:
        probe.execute('CREATE VIRTUAL TABLE fts_probe USING fts5(content)')
        fts=True
    except sqlite3.OperationalError:
        fts=False
    finally:
        probe.close()
    data={'python':platform.python_version(),'platform':platform.system(),'sqlite':sqlite3.sqlite_version,
          'fts5':fts,'law_oc_configured':bool(cfg.law_oc),'ollama_allowed':cfg.ollama_allowed(),
          'chat_model_configured':bool(cfg.ollama_model),'embedding_model_configured':bool(cfg.embedding_model),
          'official_api':'NOT_TESTED','ollama':'NOT_TESTED','ego':ego_status()['status']}
    if live:
        if cfg.law_oc:
            api=LawOpenAPI(cfg.law_oc)
            try:
                laws=api.search_statutes('민법',1)
                cases=api.search_precedents('채권양도',1)
                detail=api.statute_detail(laws[0].source_id) if laws else None
                case=api.precedent_detail(cases[0].source_id) if cases else None
                data['official_api']={'status':'OK' if detail and detail.articles and case and case.full_text else 'INCOMPLETE','law_hits':len(laws),'case_hits':len(cases),
                                      'articles':len(detail.articles) if detail else 0,
                                      'case_body':bool(case and case.full_text)}
            except SourceError as exc:
                data['official_api']={'status':'ERROR','message':str(exc)}
            finally:
                api.close()
        else:
            data['official_api']='MISSING_LAW_OC'
        if cfg.ollama_allowed():
            catalog=installed_models(cfg.ollama_base_url)
            chat=choose_model(catalog,'completion',cfg.ollama_model)
            embedding=choose_model(catalog,'embedding',cfg.embedding_model)
            llm=OllamaResearcher(cfg.ollama_base_url,chat)
            models=llm.available_models()
            data['ollama']={'status':'OK' if models else 'UNREACHABLE','models':models,
                            'selected_chat_model':chat,'selected_embedding_model':embedding}
            if chat:
                try:
                    claims,limits=llm.research_claims('대한민국 민법 제1조의 조문 내용을 요약하라',
                        {'smoke-test':'민법 제1조(법원) 민사에 관하여 법률에 규정이 없으면 관습법에 의하고 관습법이 없으면 조리에 의한다.'})
                    data['ollama']['json_smoke_test']={'status':'OK','claims':len(claims),'limitations':len(limits)}
                except Exception as exc:
                    data['ollama']['json_smoke_test']={'status':'ERROR','message':str(exc)}
            if embedding:
                try:
                    vector=OllamaEmbedder(cfg.ollama_base_url,embedding).embed(['대한민국 민법 조문 검색 테스트'])[0]
                    data['ollama']['embedding_smoke_test']={'status':'OK','dimensions':len(vector)}
                except Exception as exc:
                    data['ollama']['embedding_smoke_test']={'status':'ERROR','message':str(exc)}
        else:
            data['ollama']={'status':'BLOCKED','message':'허용되지 않은 Ollama 주소입니다.'}
    return data


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true',help='Explicitly contact configured official API and Ollama')
    parser.add_argument('--check',action='store_true',help='Check SQLite, official API, Ollama chat JSON and embeddings')
    args=parser.parse_args()
    print(json.dumps(diagnose(args.live or args.check),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
