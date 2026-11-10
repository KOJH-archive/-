"""100% fictional fixtures for a no-credential UI smoke demo.

NEVER present these as Korean law, official cases, or legal guidance.
"""
from .models import StatuteHit, StatuteDetail, Article, PrecedentHit, PrecedentDetail

LAW_ID = '900001'
CASE_ID = '900002'


class FictionalDemoSource:
    demo = True
    def search_statutes(self, query, limit=12):
        # Intentionally show a fictional law regardless of query, clearly labeled in UI.
        return [StatuteHit(source_id=LAW_ID, law_id='DEMO-001', name='[가상 예시] 샘플거래법',
                           effective_date='20990101', ministry='가상 자료',
                           source_url='', source_type='FICTIONAL_DEMO')]

    def statute_detail(self, source_id):
        if source_id != LAW_ID:
            raise KeyError('가상 법령 ID가 아닙니다')
        return StatuteDetail(source_id=LAW_ID, name='[가상 예시] 샘플거래법',
                             source_type='FICTIONAL_DEMO', effective_date='20990101',
                             articles=[
                                 Article(label='제1조', title='목적', text='이 가상 법은 소프트웨어 기능의 시연을 위한 예시이다.'),
                                 Article(label='제2조', title='통지', text='샘플 거래 당사자는 가상 통지를 기록할 수 있다.'),
                                 Article(label='제3조', title='기록 확인', text='가상 통지는 예시 기록에 의해 확인된다.'),
                             ], source_url='')

    def search_precedents(self, query, limit=12, search_body=True):
        return [PrecedentHit(source_id=CASE_ID, case_number='가상2099예시1',
                             case_name='[가상 예시] 기록 확인 사건', court='가상 법원',
                             judgment_date='20991231', source_type='FICTIONAL_DEMO', source_url=''),
                PrecedentHit(source_id='900003',case_number='가상2099예시2',case_name='[가상 예시] 기록 누락 사건',
                    court='가상 법원',judgment_date='20991231',source_type='FICTIONAL_DEMO')][:limit]

    def precedent_detail(self, source_id):
        if source_id == '900003':
            return PrecedentDetail(source_id='900003',case_number='가상2099예시2',
                case_name='[가상 예시] 기록 누락 사건',court='가상 법원',judgment_date='20991231',
                source_type='FICTIONAL_DEMO',issues='가상 통지 기록이 누락된 경우의 확인 여부',
                summary='가상 기록이 누락되면 예시 절차에서 확인 표시를 할 수 없다.',
                referenced_articles='[가상 예시] 샘플거래법 제3조',
                full_text='【주 문】\n가상 확인 요청을 받아들이지 않는다.\n【이 유】\n이것은 실제 판례가 아닌 가상 시험 자료이다. 가상 기록이 누락되어 확인할 수 없다.')
        if source_id != CASE_ID:
            raise KeyError('가상 판례 ID가 아닙니다')
        return PrecedentDetail(source_id=CASE_ID, case_number='가상2099예시1',
                               case_name='[가상 예시] 기록 확인 사건', court='가상 법원',
                               judgment_date='20991231', source_type='FICTIONAL_DEMO',
                               issues='가상 통지 기록의 확인 여부',
                               summary='가상 기록이 존재하면 예시 절차에서 확인 표시를 할 수 있다.',
                               referenced_articles='[가상 예시] 샘플거래법 제3조',
                               full_text='【주 문】\n가상 확인 요청을 받아들인다.\n【이 유】\n이 문장은 소프트웨어 시험용으로 만든 가상 판결문이다. 실제 판례가 아니다. 가상 기록이 존재한다.',
                               source_url='')
