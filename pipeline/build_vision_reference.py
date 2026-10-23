"""Build a provenance-labelled recognition guide, excluded from the RAG corpus."""
from pathlib import Path
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from pipeline.pdf_pipeline import ROOT,read_json,write_json,digest

SYMBOLS=[('GHS01','exploding_bomb','폭발하는 폭탄','폭발 위험 등','Im9','GHS01'),
('GHS02','flame','불꽃','인화성 등','Im3','GHS02'),
('GHS03','flame_over_circle','원 위의 불꽃','산화성','Im10','GHS06'),
('GHS04','gas_cylinder','가스용기','고압가스','Im7','GHS07'),
('GHS05','corrosion','부식','금속 부식 / 피부·눈 손상 등','Im6','GHS08'),
('GHS06','skull_and_crossbones','해골과 뼈','급성독성','Im4','GHS03'),
('GHS07','exclamation_mark','느낌표','자극성·유해성 등','Im2','GHS09'),
('GHS08','health_hazard','건강 유해성','발암성·호흡기 과민성 등','Im5','GHS04'),
('GHS09','environment','환경','수생환경 유해성','Im8','GHS05')]
SOURCE_URL='https://www.safeworkaustralia.gov.au/safety-topic/hazards/chemicals/classifying-chemicals/using-ghs'

def main():
 cfg=read_json(ROOT/'pipeline/config.json');data=(ROOT/cfg['input_directory']).resolve()
 source=data/cfg['documents'][0]['filename']
 if digest(source)!=cfg['documents'][0]['sha256']:raise ValueError('Source hash changed')
 assets=ROOT/'pipeline_artifacts/vision/reference-icons';assets.mkdir(parents=True,exist_ok=True)
 page=PdfReader(source).pages[104]
 for im in page.images:im.image.save(assets/(im.name.split('.')[0]+'.png'))
 dictionary={'version':'safeops-ghs-v1','standard_mapping_source':SOURCE_URL,'image_source':{'filename':source.name,'pdf_page':105,'printed_page':104,'sha256':digest(source)},'symbols':[{'code':code,'symbol':symbol,'name_ko':name,'general_meaning':meaning,'asset':asset+'.png','asset_sha256':digest(assets/(asset+'.png')),'source_legend_label':label} for code,symbol,name,meaning,asset,label in SYMBOLS]}
 write_json(ROOT/'pipeline/ghs_dictionary.json',dictionary)
 target=data/'SafeOps_GHS_인식참고_v1.pdf'
 pdfmetrics.registerFont(UnicodeCIDFont('HYSMyeongJo-Medium'))
 c=canvas.Canvas(str(target),pagesize=(595,842));c.setTitle('SafeOps GHS Recognition Reference - not operational guidance')
 def text(x,y,s,size=10,color='#173147'):
  c.setFillColor(color);c.setFont('HYSMyeongJo-Medium',size);c.drawString(x,y,s)
 text(32,802,'SafeOps | GHS 그림 인식 참고자료',21)
 text(32,779,'공식 코드 기준 · 그림은 제공 매뉴얼 PDF 105쪽에서 추출',10)
 text(32,761,'인식용 파생자료 / 안전작업 지침 아님 / 기본 RAG 색인 제외',10)
 for i,(code,symbol,name,meaning,asset,label) in enumerate(SYMBOLS):
  x=32+(i%3)*180;y=730-(i//3)*218
  c.setStrokeColorRGB(.82,.86,.9);c.roundRect(x,y-205,171,205,8,stroke=1,fill=0)
  text(x+10,y-20,code+'  '+name,11)
  c.drawImage(str(assets/(asset+'.png')),x+34,y-137,width=105,height=105,preserveAspectRatio=True,anchor='c')
  text(x+10,y-158,meaning,9)
  text(x+10,y-179,'매뉴얼 원문 번호: '+label,9)
  text(x+10,y-194,'공식 번호와 다름' if code!=label else '공식 번호와 같음',9)
 text(32,53,'이미지만으로 물질명·위험등급·모든 세부 유해성을 추정하지 않습니다.',10)
 text(32,34,'코드 대조: Safe Work Australia GHS 안내 (2쪽 출처 링크) | 1 / 2',9)
 c.showPage();text(32,802,'판독 규칙과 출처',21)
 lines=[('1. 표의 값은 열 제목과 함께 읽기',14),('성상 / 냄새 / 색상 / 분자식 / CAS번호를 각각 연결합니다.',11),('원문 글자를 우선 보존하고, 읽을 수 없는 값은 미확인으로 남깁니다.',11),('',8),('2. 그림과 글자·숫자는 별도로 처리하기',14),('그림 종류를 식별한 후 이 사전의 공식 코드와 연결합니다.',11),('번호만 OCR로 읽어 분류하지 않습니다. 원문 번호는 별도 보존합니다.',11),('그림 위치는 페이지 기준 좌표로 기록하고 사람이 위치를 확인합니다.',11),('',8),('3. NFPA를 GHS와 혼합하지 않기',14),('건강 / 화재 / 반응 / 특수위험의 열 제목과 원문 값을 연결합니다.',11),('NFPA의 0~4는 클수록 위험 수준이 높습니다.',11),('특수위험의 대시는 0점이나 안전함으로 바꾸지 않습니다.',11),('그림만으로 NFPA 숫자 또는 화학물질의 현재 분류를 추정하지 않습니다.',11),('',8),('4. 검증과 사용 범위',14),('이 자료는 기호 사전이며 모델을 학습시킨 결과물이 아닙니다.',11),('가성소다·암모니아 페이지의 정답은 인식 프롬프트에 넣지 않습니다.',11),('두 페이지 통과는 초기 검증일 뿐, 9종 전체의 실문서 성능은 아닙니다.',11),('검토 전 판독 결과는 원본 텍스트나 활성 인덱스를 덮어쓰지 않습니다.',11),('',8),('출처와 작성 이력',14),('그림: 연구실 안전관리 매뉴얼 PDF 105쪽 / 인쇄 104쪽',11),('공식 코드 대조: Safe Work Australia, Using the GHS',11),('작성: SafeOps 파생자료 / 2026-10-23 / v1',11)]
 y=758
 for s,size in lines:text(32,y,s,size);y-=23
 text(32,139,'공식 GHS 코드 안내 열기',11);c.linkURL(SOURCE_URL,(30,135,300,153),relative=0)
 nfpa='https://docinfofiles.nfpa.org/files/AboutTheCodes/704/NFPA704_HC2012_QCard.pdf'
 text(32,114,'NFPA 704 / HazCom 비교표 열기',11);c.linkURL(nfpa,(30,110,330,128),relative=0)
 text(32,70,'원본 해시: '+digest(source)[:32]+'…',9)
 text(32,35,'기호 원본의 일괄 재학습·운영 안전 판정용 자료가 아닙니다. | 2 / 2',9)
 c.save()
 cfg['recognition_references']=[{'filename':target.name,'sha256':digest(target),'purpose':'recognition_reference_only','rag_ingest':False,'generated':True}]
 write_json(ROOT/'pipeline/config.json',cfg)
 print(target)
if __name__=='__main__':main()
