from pathlib import Path
from streamlit.testing.v1 import AppTest
from legal_studio.llm import OllamaResearcher


def test_streamlit_demo_research_and_mode_switch(monkeypatch,tmp_path):
    monkeypatch.setenv('DEMO_MODE','1')
    monkeypatch.setenv('ENABLE_LLM','0')
    monkeypatch.setenv('DB_PATH',str(tmp_path/'ui.db'))
    monkeypatch.setattr(OllamaResearcher,'available_models',lambda self:[])
    monkeypatch.setattr('legal_studio.model_catalog.installed_models',lambda url:[])
    at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'ui.py'),default_timeout=20).run()
    assert not at.exception
    next(b for b in at.button if b.label=='리서치 실행').click().run()
    assert not at.exception
    assert at.session_state['last_result'].source_mode=='fictional_demo'
    assert at.session_state['last_result'].steps
    next(b for b in at.button if b.label=='유사 판례 찾기').click().run()
    assert not at.exception
    assert at.session_state['similar_result'].results
    at.toggle[0].set_value(False).run()
    assert not at.exception
    assert 'last_result' not in at.session_state
    assert 'similar_result' not in at.session_state
