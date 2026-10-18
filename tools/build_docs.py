"""Generate synchronized capstone deliverables from the current release documentation."""
from pathlib import Path
import html,json,re
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,Image
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib import colors
from docx import Document
from docx.shared import Inches
from pptx import Presentation
from pptx.util import Inches as PInches,Pt
from pptx.dml.color import RGBColor
R=Path(__file__).resolve().parents[1];D=R/'docs';checks=json.loads((R/'data/release_checks.json').read_text())
sections=[('Release results',f"{checks['core']['tests_run']} core regressions; {checks['ui']['checks_passed']} workflow checks; {checks['browser']['checks_passed']} local browser checks. Failures: {checks['core']['failures']}; errors: {checks['core']['errors']}. These checks do not establish live provider quality, deployed rebuild completion or independent expert usefulness.")]+[(name,(D/file).read_text()) for name,file in [('Corrective release','RELEASE_NOTES.md'),('Evidence and methods','DATA_SOURCES.md'),('Analyst workflow','USER_GUIDE.md'),('Planning and evaluation','PLAN.md')]]
styles=getSampleStyleSheet();styles.add(ParagraphStyle(name='BodyBoundary',fontSize=10,leading=15,spaceAfter=10));styles['Title'].fontName='Times-Roman';styles['Heading1'].textColor=colors.HexColor('#AB2436')
story=[Paragraph('BOUNDARY',styles['Title']),Paragraph('Franchise research studio — corrective release',styles['Heading2']),Paragraph('18 October 2026 · Independent educational capstone',styles['Normal']),Spacer(1,20)]
doc=Document();doc.add_heading('Boundary — corrective capstone release',0);doc.add_paragraph('18 October 2026 · Franchise research studio')
for i,(title,body) in enumerate(sections):
 if i:story.append(PageBreak())
 story.append(Paragraph(title,styles['Heading1']));doc.add_heading(title,1)
 for para in body.split('\n\n'):
  para=para.strip()
  if not para or para.startswith('#'):continue
  story.append(Paragraph(html.escape(para).replace('\n','<br/>'),styles['BodyBoundary']));doc.add_paragraph(para)
 if i==0:
  shot=D/'previews/dark-desk.png';story.append(Image(str(shot),width=455,height=332));doc.add_picture(str(shot),width=Inches(6))
SimpleDocTemplate(str(D/'Capstone_Report.pdf'),title='Boundary corrective capstone release',leftMargin=42,rightMargin=42).build(story);doc.save(D/'Capstone_Report.docx')
slides=[('Boundary','Evidence, decisions and an inspectable research trail'),('The analyst workflow','Scout a role → compare evidence → confirm identity\nPlan the XI and every bowling over\nInspect uncertainty → preserve the reasoning'),('Evidence and identity','6,392 eligible men’s matches; 141,377 player-match records\nStrict dates, archive hashes and phase reconciliation\nUnique unregistered planning IDs; partial roster verification disclosed'),('Supported planning','Exactly eleven; overseas, keeper and role constraints\n36 PP / 60 middle / 24 death balls; max 24 per player\nAvailability, locks, styles and explicit cost assumptions'),('The bounded assistant','Approved tools retrieve the active scenario\nOnly locally rendered tool facts reach the brief\nDeferred excess calls, scoped cache and outage clearing'),('Prediction honesty','Training before 2023; validation 2023; test 2024 onward\nResearch model failed the stronger baseline gate\nServe baseline; keep model results open to scrutiny'),('Private session records','Random session + franchise scope\nNo legacy shared journal reads\nExport work; authenticated team accounts remain future work'),('Interface and accessibility','Ten franchise accents and bundled crests\nIPL vector text mark; Light and Dark modes\nResponsive typography and themed research tables'),('Actual validation',f"{checks['core']['tests_run']} core regressions\n{checks['ui']['checks_passed']} workflow checks\n{checks['browser']['checks_passed']} local browser checks"),('Remaining evidence gaps','Verify complete current squads and availability\nAuthenticate durable shared team access\nMeasure expert usefulness and live provider quality')]
prs=Presentation();prs.slide_width=PInches(13.333);prs.slide_height=PInches(7.5)
for i,(title,body) in enumerate(slides):
 slide=prs.slides.add_slide(prs.slide_layouts[6]);slide.background.fill.solid();slide.background.fill.fore_color.rgb=RGBColor.from_string('101820')
 for top,height,text,size,col in [(.5,.4,f'BOUNDARY / CAPSTONE RESEARCH                         {i+1:02d}',11,'FF8798'),(1.4,1.1,title,36,'E8EDF1'),(3,4,body,24,'A8B8C5')]:
  box=slide.shapes.add_textbox(PInches(.8),PInches(top),PInches(11.8),PInches(height));tf=box.text_frame;tf.word_wrap=True
  for j,line in enumerate(text.split('\n')):
   q=tf.paragraphs[0] if j==0 else tf.add_paragraph();q.text=line;q.font.size=Pt(size);q.font.color.rgb=RGBColor.from_string(col);q.space_after=Pt(24)
prs.save(D/'Capstone_Presentation.pptx');print('Synchronized PDF, DOCX and 10-slide PPTX.')
