"""Cross-team and cross-theme Streamlit workflows; never calls the live provider."""
import json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from streamlit.testing.v1 import AppTest
checks=[]
def clean(a,label):
 assert not a.exception,(label,[x.message for x in a.exception]);checks.append(label)
def find(items,label):return next(x for x in items if x.label==label)
with tempfile.TemporaryDirectory() as d:
 os.environ['BOUNDARY_RUNTIME_DIR']=d
 a=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run();clean(a,'initial decision desk')
 pages=['Decision desk','Scouting & comparison','Squad & auction scenarios','Player dossier','Match research','Decision journal','Evaluation & sources','Settings']
 for theme in ['Light','Dark']:
  a.sidebar.segmented_control[0].set_value(theme).run()
  for page in pages:
   a.sidebar.radio[0].set_value(page).run();clean(a,theme+' / '+page)
 a.sidebar.segmented_control[0].set_value(None).run();clean(a,'theme cannot deselect into missing state');assert a.sidebar.segmented_control[0].value=='Dark'
 a.sidebar.radio[0].set_value('Squad & auction scenarios').run()
 for team in ['CSK','DC','GT','KKR','LSG','MI','PBKS','RCB','RR','SRH']:
  a.sidebar.selectbox[0].set_value(team).run();clean(a,'workload XI / '+team);assert not a.warning,(team,[x.value for x in a.warning]);assert find(a.metric,'Allocated balls').value=='120'
 a.sidebar.selectbox[0].set_value('RCB').run();names=find(a.multiselect,'Unavailable / exclude').options;find(a.multiselect,'Unavailable / exclude').set_value(names).run();clean(a,'all unavailable abstains');assert a.warning
 find(a.multiselect,'Unavailable / exclude').set_value([]).run();find(a.checkbox,'Apply XI budget').check().run();clean(a,'budget editor');assert not a.warning,([x.value for x in a.warning],[(x.label,x.value) for x in a.number_input],[(x.label,x.value) for x in a.multiselect])
 find(a.number_input,'XI scenario budget (₹ Cr)').set_value(1.).run();clean(a,'insufficient budget abstains');assert a.warning
 find(a.checkbox,'Apply XI budget').uncheck().run()
 a.sidebar.radio[0].set_value('Scouting & comparison').run();find(a.selectbox,'Competition').set_value('BBL').run();find(a.selectbox,'Phase').set_value('Powerplay').run();find(a.number_input,'Minimum phase balls').set_value(60).run();clean(a,'scouting alternate league phase')
 a.sidebar.radio[0].set_value('Decision desk').run();assert any('BBL' in x.value and 'Powerplay' in x.value for x in a.markdown);checks.append('filters travel to decision desk')
 find(a.button,'Prepare brief').click().run();clean(a,'local tool-backed brief');assert 'brief' in a.session_state
 find(a.button,'Save private brief').click().run();a.sidebar.radio[0].set_value('Decision journal').run();clean(a,'private journal save');assert len(a.expander)==1
 a.sidebar.selectbox[0].set_value('MI').run();clean(a,'team journal isolated');assert len(a.expander)==0
 a.sidebar.selectbox[0].set_value('RCB').run();assert len(a.expander)==1;checks.append('original team journal retained')
 a.sidebar.radio[0].set_value('Decision desk').run();find(a.radio,'Briefing mode').set_value('DeepSeek analyst').run()
 with patch('agent.ask',side_effect=RuntimeError('controlled outage')):find(a.button,'Prepare brief').click().run()
 clean(a,'failed request clears previous brief');assert 'brief' not in a.session_state;assert a.error
 a.sidebar.radio[0].set_value('Player dossier').run();find(a.text_input,'Player name or scorecard alias').set_value('T Natarajan').run();clean(a,'canonical identity dossier');assert find(a.selectbox,'Confirm identity').value['player_id']=='ce794613'
 a.sidebar.radio[0].set_value('Decision journal').run();find(a.sidebar.button,'Start a fresh private session').click().run();clean(a,'fresh session hides old journal');assert len(a.expander)==0
 # A separate browser session cannot see this session’s records.
 b=AppTest.from_file(str(ROOT/'app.py'),default_timeout=60).run();b.sidebar.radio[0].set_value('Decision journal').run();clean(b,'second visitor journal isolated');assert len(b.expander)==0
 (ROOT/'data/ui_results.json').write_text(json.dumps({'checks_passed':len(checks),'checks':checks,'scope':'Headless Streamlit, ten team workload plans, themes, isolation, filtered evidence and controlled outage. No live-provider test.'},indent=2));print('UI checks passed:',len(checks))
