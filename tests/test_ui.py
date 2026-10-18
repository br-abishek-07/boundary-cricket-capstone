"""Headless Streamlit workflow checks; no provider calls or persistent user data."""
import json,os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from streamlit.testing.v1 import AppTest
checks=[]
with tempfile.TemporaryDirectory() as d:
 os.environ['BOUNDARY_RUNTIME_DIR']=d
 a=AppTest.from_file(str(ROOT/'app.py'),default_timeout=45).run()
 assert not a.exception,[x.message for x in a.exception]
 for page in ['Scouting & comparison','Squad & auction scenarios','Player dossier','Match research','Decision journal','Evaluation & SWOT','Settings','Decision desk']:
  a.sidebar.radio[0].set_value(page).run();assert not a.exception,(page,[x.message for x in a.exception]);checks.append(page)
 a.radio[0].set_value('Saved demonstration').run();next(x for x in a.button if x.label=='Prepare brief').click().run();assert not a.exception;checks.append('saved demonstration')
 next(x for x in a.button if x.label=='Save to journal').click().run();assert not a.exception
 a.sidebar.radio[0].set_value('Decision journal').run();assert not a.exception;assert len(a.expander)>0;checks.append('journal save/read')
 a.sidebar.radio[0].set_value('Squad & auction scenarios').run();a.checkbox[0].check().run();assert not a.exception;checks.append('budget scenario')
 a.multiselect[0].set_value(a.multiselect[0].options).run();assert not a.exception;assert any('Not enough' in x.value for x in a.warning);checks.append('infeasible scenario')
 (ROOT/'data/ui_results.json').write_text(json.dumps({'checks_passed':len(checks),'checks':checks,'scope':'Headless UI behavior; desktop/mobile visual rendering separately inspected. No live API requests.'},indent=2))
 print('UI checks passed:',len(checks))
