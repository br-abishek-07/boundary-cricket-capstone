"""Behavioral checks for the integrated release. No live API charges."""
import collections,json,os,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analytics import load,scout,roster_scores,optimize,player_interval
from prediction import chronology,features,predict,initial_state,metrics
from agent import ask,dispatch,safe
from match_data import build
import storage
ROOT=Path(__file__).resolve().parents[1]
class Integration(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.p,cls.s,cls.a=load();cls.model=json.loads((ROOT/'data/prediction_model.json').read_text());cls.m=pd.read_csv(ROOT/'data/matches.csv.gz',keep_default_na=False,dtype={'match_id':str,'season':str})
 def test_match_player_unique(self):self.assertFalse(self.p.duplicated(['match_id','player_id']).any())
 def test_matches_unique(self):self.assertFalse(self.m.match_id.duplicated().any())
 def test_counts_nonnegative(self):self.assertTrue((self.p[['runs','balls','legal_balls','wickets','dismissals']]>=0).all().all())
 def test_voided_excluded(self):self.assertNotIn('1473495',set(self.m.match_id))
 def test_coverage(self):self.assertEqual(set(self.m.competition),{'IPL','BBL','SMAT','Hundred','T20I'})
 def test_minimum_sample(self):self.assertTrue((scout(self.p,min_balls=120).balls>=120).all())
 def test_empty_shortlist_stable_schema(self):self.assertIn('score',scout(self.p,since='2090-01-01').columns)
 def test_cutoff_no_future(self):
  x=scout(self.p,until='2025-01-01');past=self.p[self.p.date<'2025-01-01'];pd.testing.assert_frame_equal(x,scout(past,until='2025-01-01'))
 def test_phase_sample(self):
  r=scout(self.p,min_balls=100,discipline='Bowling',phase='Death');self.assertTrue((r.legal_balls>=100).all());self.assertNotIn('wickets',r)
 def test_no_alias_duplication(self):self.assertFalse(scout(self.p,min_balls=1).player_id.duplicated().any())
 def test_all_franchise_XI(self):
  for team in self.s.franchise_id.unique():
   r=optimize(roster_scores(self.p,self.s,team));self.assertTrue(r['ok'],team);self.assertEqual(len(r['players']),11);self.assertLessEqual(r['overseas'],4);self.assertGreaterEqual(r['keepers'],1);self.assertGreaterEqual(r['bowlers'],5)
 def test_excluded_player_absent(self):
  roster=roster_scores(self.p,self.s,'RCB');first=optimize(roster)['players'].player_name.iloc[0];r=optimize(roster,[first]);self.assertTrue(r['ok']);self.assertNotIn(first,r['players'].player_name.tolist())
 def test_locked_player_present(self):
  r=roster_scores(self.p,self.s,'RCB');n=r[r.role=='Batter'].player_name.iloc[-1];result=optimize(r,locked=[n]);self.assertTrue(result['ok']);self.assertIn(n,result['players'].player_name.tolist())
 def test_contradictory_lock(self):
  r=roster_scores(self.p,self.s,'RCB');n=r.player_name.iloc[0];self.assertFalse(optimize(r,excluded=[n],locked=[n])['ok'])
 def test_infeasible(self):
  r=roster_scores(self.p,self.s,'RCB');self.assertFalse(optimize(r,r.player_name.tolist())['ok'])
 def test_budget_enforced(self):
  r=roster_scores(self.p,self.s,'RCB');costs={n:1. for n in r.player_name};result=optimize(r,costs=costs,budget=11);self.assertTrue(result['ok']);self.assertLessEqual(result['cost'],11);self.assertFalse(optimize(r,costs=costs,budget=10)['ok'])
 def test_missing_prices_rejected(self):self.assertFalse(optimize(roster_scores(self.p,self.s,'RCB'),costs={},budget=20)['ok'])
 def test_all_bench_players_scored(self):
  r=roster_scores(self.p,self.s,'RCB');self.assertEqual(len(r),len(self.s[self.s.franchise_id=='RCB']));self.assertFalse(r.utility.isna().any())
 def test_interval_no_sample(self):self.assertIsNone(player_interval(self.p,'unknown')['interval'])
 def test_interval_reproducible(self):
  pid=self.p.player_id.iloc[0];self.assertEqual(player_interval(self.p,pid),player_interval(self.p,pid))
 def test_prediction_symmetry(self):
  a=predict(self.model,'RCB','CSK','Unknown','RCB');b=predict(self.model,'CSK','RCB','Unknown','RCB');self.assertAlmostEqual(a['pre']+b['pre'],1);self.assertAlmostEqual(a['post']+b['post'],1)
 def test_same_team_rejected(self):
  with self.assertRaises(ValueError):predict(self.model,'RCB','RCB')
 def test_temporal_future_invariance(self):
  cut='2025-01-01';records,_=chronology(self.m);old=[r for r in records if r['date']<cut];past,_=chronology(self.m[self.m.date<cut]);self.assertEqual(old,past)
 def test_same_date_outcome_not_a_feature(self):
  m=self.m[self.m.competition=='IPL'].head(12).copy();r,_=chronology(m);first_date=r[0]['date'];mut=m.copy();mask=mut.date==first_date;mut.loc[mask,'winner']=mut.loc[mask,'team2'];changed,_=chronology(mut);self.assertEqual(r[0]['pre'],changed[0]['pre']);self.assertEqual(r[0]['post'],changed[0]['post'])
 def test_probability_bounds(self):
  for a in self.s.franchise_id.unique():self.assertTrue(0<predict(self.model,a,'RCB' if a!='RCB' else 'MI')['pre']<1)
 def test_brier_baseline(self):self.assertEqual(metrics([0,1],[.5,.5])['brier'],.25)
 def test_tool_allowlist(self):
  with self.assertRaises(ValueError):dispatch('execute_code',{},self.p,self.s,self.model,'MI','2026-10-18')
 def test_tool_type_validation(self):
  with self.assertRaises(ValueError):dispatch('scout_players',{'min_balls':'120'},self.p,self.s,self.model,'MI','2026-10-18')
 def test_historical_prediction_guard(self):self.assertIn('error',dispatch('match_prediction',{'team1':'MI','team2':'RCB'},self.p,self.s,self.model,'MI','2010-01-01'))
 def test_unknown_player_abstains(self):self.assertIn('No player',dispatch('player_dossier',{'name':'Nobody XYZ'},self.p,self.s,self.model,'MI','2026-10-18')['result'])
 def test_json_safe(self):self.assertEqual(json.dumps(safe({'x':float('nan')}),allow_nan=False),'{"x": null}')
 def test_missing_key_no_call(self):
  with patch('agent.provider') as provider:
   with self.assertRaises(ValueError):ask('test',self.p,self.s,self.model,'MI','2026-10-18','')
   provider.assert_not_called()
 def test_agent_tool_orchestration_and_cache(self):
  calls=[({'content':None,'tool_calls':[{'id':'t1','type':'function','function':{'name':'player_dossier','arguments':'{"name":"Nobody XYZ"}'}}]},{}),({'content':'No matching evidence was found [S1].'}, {'total_tokens':20})]
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'BOUNDARY_RUNTIME_DIR':d}),patch('agent.provider',side_effect=calls) as provider:
   r=ask('Unknown player?',self.p,self.s,self.model,'MI','2026-10-18','test-key');self.assertEqual(len(r['trace']),1);self.assertTrue(r['citations_present']);r2=ask('Unknown player?',self.p,self.s,self.model,'MI','2026-10-18','test-key');self.assertTrue(r2['cached']);self.assertEqual(provider.call_count,2)
 def test_agent_rejects_unretrieved_answer(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'BOUNDARY_RUNTIME_DIR':d}),patch('agent.provider',return_value=({'content':'Invented answer'},{})) as provider:
   with self.assertRaises(RuntimeError):ask('Numbers?',self.p,self.s,self.model,'MI','2026-10-18','test-key')
   self.assertEqual(provider.call_count,3)
 def test_allowance_persistent(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'BOUNDARY_RUNTIME_DIR':d}):
   storage.reserve_call(2);storage.reserve_call(2)
   with self.assertRaises(RuntimeError):storage.reserve_call(2)
 def test_journal_roundtrip(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'BOUNDARY_RUNTIME_DIR':d}):
   storage.save('briefs','test',{'team':'MI','cost':5});self.assertEqual(storage.records()[0]['payload']['cost'],5)
 def test_parser_extras_wickets_and_gender(self):
  sample={'info':{'gender':'male','dates':['2020-01-01'],'season':2020,'teams':['A','B'],'players':{'A':['Batter'],'B':['Bowler']},'registry':{'people':{'Batter':'bat','Bowler':'bowl'}}},'innings':[{'team':'A','overs':[{'over':0,'deliveries':[{'batter':'Batter','bowler':'Bowler','runs':{'batter':0,'total':1},'extras':{'wides':1}},{'batter':'Batter','bowler':'Bowler','runs':{'batter':4,'total':5},'extras':{'noballs':1}},{'batter':'Batter','bowler':'Bowler','runs':{'batter':0,'total':0},'wickets':[{'kind':'run out','player_out':'Batter'}]}]}]}]}
  with tempfile.TemporaryDirectory() as d:
   src=Path(d)/'source';src.mkdir();dest=Path(d)/'output'
   with zipfile.ZipFile(src/'ipl_json.zip','w') as z:
    z.writestr('123.json',json.dumps(sample));female=json.loads(json.dumps(sample));female['info']['gender']='female';z.writestr('124.json',json.dumps(female));z.writestr('1473495.json',json.dumps(sample))
   build(src,dest);rows=pd.read_csv(dest/'match_players.csv.gz').set_index('player_id');self.assertEqual(rows.loc['bat','balls'],2);self.assertEqual(rows.loc['bat','runs'],4);self.assertEqual(rows.loc['bowl','legal_balls'],1);self.assertEqual(rows.loc['bowl','conceded'],6);self.assertEqual(rows.loc['bowl','wickets'],0);self.assertEqual(rows.loc['bat','dismissals'],1);self.assertEqual(json.loads((dest/'audit.json').read_text())['matches'],1)

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Integration);r=unittest.TextTestRunner(verbosity=2).run(suite)
 (ROOT/'data/test_results.json').write_text(json.dumps({'tests_run':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'scope':'Offline ingestion, cutoff integrity, scouting, solver, temporal prediction, bounded agent orchestration, budget and persistence. Live AI quality and expert review are not included.','tests':[n for n in unittest.defaultTestLoader.getTestCaseNames(Integration)]},indent=2));sys.exit(not r.wasSuccessful())
