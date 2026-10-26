"""순번은 생성 당시 docs에 매핑하며, 중복 제거된 sources를 인덱싱하지 않는다."""
import re
import unittest
from types import SimpleNamespace
from tests.test_chat_persistence import load_functions


class DocumentCitationTests(unittest.TestCase):
    def setUp(self):
        self.resolve, = load_functions('resolve_document_citations', 'doc_label', namespace={'re': re})[:1]
        self.docs = [SimpleNamespace(metadata={'filename': '연구실 안전관리 매뉴얼.pdf',
                                              'pdf_page_start': n}) for n in range(1, 9)]

    def test_abbreviated_multiple_numbers_keep_both_pages(self):
        answer, sources = self.resolve('대응 (문서 5, 3).', self.docs)
        self.assertEqual(answer, '대응 (연구실 안전관리 매뉴얼 p.5, 연구실 안전관리 매뉴얼 p.3).')
        self.assertEqual(len(sources), 2)
        self.assertTrue(sources[1].endswith('p.3'))

    def test_repeated_keyword_and_deduplication(self):
        answer, sources = self.resolve('(문서 6, 문서 8, 6)', self.docs)
        self.assertNotIn('문서 6', answer)
        self.assertEqual(len(sources), 2)

    def test_invalid_number_is_not_silently_reassigned(self):
        answer, sources = self.resolve('(문서 99, 3)', self.docs)
        self.assertIn('출처 확인 필요', answer)
        self.assertEqual(sources, ['연구실 안전관리 매뉴얼.pdf p.3'])

    def test_brackets(self):
        answer, _ = self.resolve('[문서 5, 3]', self.docs)
        self.assertNotIn('[문서', answer)

    def test_no_citation_does_not_invent_one(self):
        self.assertEqual(self.resolve('확인이 필요합니다.', self.docs), ('확인이 필요합니다.', []))
