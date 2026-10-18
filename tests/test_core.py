"""Corrective release regression suite. Provider fixtures never spend API credit."""
import json,os,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from analytics import load,scout,roster_scores,optimize,resolve,squads_asof,player_interval,select_window
from prediction import chronology,predict,metrics,venue_key
from match_data import build
from agent import ask,dispatch,safe
import storage

class Release(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.p,cls.s,cls.a=load();cls.model=json.loads((ROOT/'data/prediction_model.json').read_text());cls.report=json.loads((ROOT/'data/prediction_report.json').read_text());cls.m=pd.read_csv(ROOT/'data/matches.csv.gz',dtype={'match_id':str,'season':str},keep_default_na=False);cls.owner=storage.scope('test-session','RCB')
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'BOUNDARY_RUNTIME_DIR':self.temp.name});self.env.start()
 def tearDown(self):self.env.stop();self.temp.cleanup()
 def test_01_unique_and_counts(self):
  self.assertEqual(len(self.m),6392);self.assertEqual(len(self.p),141377);self.assertFalse(self.m.match_id.duplicated().any());self.assertFalse(self.p.duplicated(['match_id','player_id']).any());self.assertNotIn('1473495',set(self.m.match_id));self.assertTrue((self.p[['runs','balls','wickets','legal_balls','dismissals','conceded']]>=0).all().all())
 def test_02_phase_reconciliation(self):
  for target,suffix in [('runs','runs'),('balls','balls'),('legal_balls','legal'),('conceded','conceded'),('wickets','wickets'),('dismissals','dismissals')]:
   with self.subTest(metric=target):self.assertTrue((self.p[target]==self.p[[ph+'_'+suffix for ph in ['pp','mid','death']]].sum(axis=1)).all())
 def test_03_reduced_chase(self):
  z=self.p[(self.p.match_id=='1082648')&(self.p.team=='Kolkata Knight Riders')];self.assertGreater(z.balls.sum(),z.pp_balls.sum());self.assertGreater(z.death_balls.sum(),0)
 def test_04_raw_totals_unchanged(self):
  old=pd.read_csv(ROOT.parent/'capstone/data/match_players.csv.gz',dtype={'match_id':str,'player_id':str}) if (ROOT.parent/'capstone/data/match_players.csv.gz').exists() else None
  if old is None:self.skipTest('Original audit snapshot is not shipped; phase and fixture checks remain reproducible.')
  cols=['runs','balls','dismissals','conceded','legal_balls','wickets'];a=old.set_index(['match_id','player_id'])[cols].sort_index();b=self.p.set_index(['match_id','player_id'])[cols].sort_index();pd.testing.assert_frame_equal(a,b)
 def test_05_identity_aliases(self):
  for query,pid in [('T Natarajan','ce794613'),('Devdutt Padikkal','2c25d4f5')]:
   with self.subTest(query=query):self.assertEqual(resolve(self.p,query)[0]['player_id'],pid)
  self.assertFalse(self.s.cricsheet_id.duplicated().any());self.assertEqual(len(self.s[self.s.player_name=='Naman Tiwari']),1);self.assertEqual(resolve(self.p,'Nobody XYZ'),[]);self.assertGreater(len(resolve(self.p,'Sharma')),1)
 def test_06_dated_trades_and_historical_guard(self):
  with self.assertRaises(ValueError):squads_asof(self.s,'2025-12-31')
  before=squads_asof(self.s,'2026-10-14');after=squads_asof(self.s,'2026-10-15');self.assertEqual(before[before.player_name=='T Natarajan'].franchise_id.iloc[0],'DC');self.assertEqual(after[after.player_name=='T Natarajan'].franchise_id.iloc[0],'SRH')
 def test_07_cutoff_invariance(self):
  z=scout(self.p,since='2023-01-01',until='2025-01-01');pd.testing.assert_frame_equal(z,scout(self.p[self.p.date<'2025-01-01'],since='2023-01-01',until='2025-01-01'))
 def test_08_phase_filter_and_samples(self):
  r=scout(self.p,min_balls=100,discipline='Bowling',phase='Death');self.assertTrue((r.legal_balls>=100).all());self.assertFalse(r.player_id.duplicated().any());self.assertTrue(np.isfinite(r.score).all())
 def test_09_competitions_separate(self):
  all_=scout(self.p,'ALL',min_balls=120);self.assertIn('competition',all_);self.assertFalse(all_.duplicated(['competition','player_id']).any())
  for comp in all_.competition.unique():
   one=scout(self.p,comp,min_balls=120).set_index('player_id');g=all_[all_.competition==comp].set_index('player_id');pd.testing.assert_series_equal(g.score.sort_index(),one.score.sort_index())
 def test_10_interval_same_scope(self):
  pid=resolve(self.p,'Virat Kohli')[0]['player_id'];a=player_interval(self.p,pid,'Batting','2026-10-18','2024-01-01','IPL','Powerplay');z=select_window(self.p,'IPL','2024-01-01','2026-10-18','Powerplay');z=z[z.player_id==pid];self.assertAlmostEqual(a['rate'],100*z.runs.sum()/z.balls.sum());self.assertEqual(a,player_interval(self.p,pid,'Batting','2026-10-18','2024-01-01','IPL','Powerplay'))
 def test_11_all_ten_workload_plans(self):
  for team in sorted(self.s.franchise_id.unique()):
   with self.subTest(team=team):
    result=optimize(roster_scores(self.p,self.s,team),min_spin=1,min_pace=2);self.assertTrue(result['ok'],result);r=result['players'];self.assertEqual(len(r),11);self.assertLessEqual(result['overseas'],4);self.assertGreaterEqual(result['keepers'],1);self.assertFalse(r.evidence_missing.any());cols=['pp_allocated_balls','mid_allocated_balls','death_allocated_balls'];self.assertEqual(r[cols].sum().tolist(),[36,60,24]);self.assertTrue((r[cols].sum(axis=1)<=24).all());self.assertTrue((r[r.bowling_capacity==0][cols].sum(axis=1)==0).all());self.assertGreaterEqual(len(r[(r.attack_type=='Spin')&(r.bowling_capacity>0)]),1)
 def test_12_availability_and_locks(self):
  roster=roster_scores(self.p,self.s,'RCB');first=optimize(roster)['players'].iloc[0].player_name;result=optimize(roster,excluded=[first]);self.assertTrue(result['ok']);self.assertNotIn(first,result['players'].player_name.tolist());self.assertFalse(optimize(roster,excluded=[first],locked=[first])['ok']);self.assertFalse(optimize(roster,excluded=roster.player_name.tolist())['ok'])
 def test_13_budget_validation(self):
  r=roster_scores(self.p,self.s,'MI');costs={n:1 for n in r.player_name};self.assertTrue(optimize(r,costs=costs,budget=11)['ok']);self.assertFalse(optimize(r,costs=costs,budget=10)['ok']);self.assertFalse(optimize(r,costs={},budget=20)['ok']);costs[r.player_name.iloc[0]]=float('nan');self.assertFalse(optimize(r,costs=costs,budget=20)['ok'])
 def test_14_override_validation(self):
  r=roster_scores(self.p,self.s,'RCB');n=r.player_name.iloc[0]
  for o in [{'capacity':4},{'capacity':4,'reason':'analyst','pp':-1},{'capacity':4,'reason':'analyst','death':float('nan')}]:self.assertFalse(optimize(r,overrides={n:o})['ok'])
 def test_15_prediction_gate_and_symmetry(self):
  self.assertFalse(self.model['gate_passed']);self.assertGreaterEqual(self.report['test']['post']['brier'],self.report['test']['training_chase_baseline']['brier'])
  a=predict(self.model,'RCB','CSK','Unknown','RCB');b=predict(self.model,'CSK','RCB','Unknown','RCB');self.assertEqual(a['pre'],.5);self.assertAlmostEqual(a['post']+b['post'],1);self.assertEqual(metrics([0,1],[.5,.5])['brier'],.25)
 def test_16_venue_aliases(self):
  self.assertEqual(venue_key('M Chinnaswamy Stadium, Bengaluru'),venue_key('M.Chinnaswamy Stadium'));self.assertEqual(venue_key('Feroz Shah Kotla'),venue_key('Arun Jaitley Stadium, Delhi'))
 def test_17_forecast_future_invariance(self):
  records,_=chronology(self.m);past,_=chronology(self.m[self.m.date<'2025-01-01']);self.assertEqual([r for r in records if r['date']<'2025-01-01'],past)
 def test_18_tool_filters_and_allowlist(self):
  for name,args in [('execute_code',{}),('scout_players',{'min_balls':'120'}),('optimize_xi',{'budget':999})]:
   with self.assertRaises(ValueError):dispatch(name,args,self.p,self.s,self.model,'MI','2026-10-18',{})
  self.assertEqual(dispatch('match_prediction',{'team1':'MI','team2':'RCB'},self.p,self.s,self.model,'MI','2010-01-01',{})['kind'],'insufficient')
 def test_19_agent_dossier_phase_scope(self):
  context={'since':'2024-01-01','phase':'Powerplay','competition':'IPL'};r=dispatch('player_dossier',{'name':'Virat Kohli'},self.p,self.s,self.model,'RCB','2026-10-18',context);z=select_window(self.p,'IPL','2024-01-01','2026-10-18','Powerplay');z=z[z.player_id==resolve(self.p,'Virat Kohli')[0]['player_id']];self.assertEqual(r['records'][0]['runs'],int(z.runs.sum()))
 def test_20_agent_inherits_exact_scenario(self):
  scenario={'excluded':['A'],'locked':['B'],'budget':11,'costs':{'A':1},'min_spin':2,'min_pace':3,'overrides':{}}
  with patch('agent.optimize',return_value={'ok':False,'reason':'test'}) as opt:
   dispatch('optimize_xi',{},self.p,self.s,self.model,'MI','2026-10-18',scenario);self.assertEqual(opt.call_args.kwargs,scenario)
 def tool(self,i,name='player_dossier',args=None):return {'id':f't{i}','type':'function','function':{'name':name,'arguments':json.dumps(args or {'name':'Virat Kohli'})}}
 def run_agent(self,replies,question='Compare evidence'):
  with patch('agent.provider',side_effect=replies) as provider:return ask(question,self.p,self.s,self.model,'RCB','2026-10-18','test-key',self.owner,{'phase':'All'}),provider
 def test_21_grounded_cache(self):
  result,provider=self.run_agent([({'tool_calls':[self.tool(1)]},{}),({'content':'{"selected_fact_ids":["F1"],"next_actions":["video"]}'},{})]);self.assertEqual(result['status'],'grounded');self.assertEqual(len(result['facts']),1)
  with patch('agent.provider') as p:r=ask('Compare evidence',self.p,self.s,self.model,'RCB','2026-10-18','test-key',self.owner,{'phase':'All'});self.assertTrue(r['cached']);p.assert_not_called()
 def test_22_failed_tools_no_invention(self):
  r,_=self.run_agent([({'tool_calls':[self.tool(1,args={'name':'Nobody XYZ'})]},{}),({'content':'999 runs [F1]'},{}),({'content':'{"selected_fact_ids":["F1"],"next_actions":[]}'},{})]);self.assertEqual(r['status'],'insufficient');self.assertNotIn('999',r['text']);self.assertEqual(r['facts'],{})
 def test_23_unknown_fact_rejected(self):
  r,_=self.run_agent([({'tool_calls':[self.tool(1)]},{}),({'content':'{"selected_fact_ids":["F999"],"next_actions":[]}'},{}),({'content':'{"selected_fact_ids":["F1"],"next_actions":[]}'},{})]);self.assertEqual(list(r['facts']),['F1']);self.assertNotIn('F999',r['text'])
 def test_24_tool_overflow_protocol(self):
  calls=[self.tool(i,args={'name':n}) for i,n in enumerate(['Virat Kohli','Rohit Sharma','MS Dhoni','Jasprit Bumrah','Ravindra Jadeja'])];r,provider=self.run_agent([({'tool_calls':calls},{}),({'content':'{"selected_fact_ids":["F1"],"next_actions":[]}'},{})]);self.assertEqual(len(r['trace']),5);self.assertEqual(r['trace'][-1]['result']['kind'],'deferred');messages=provider.call_args.args[0];self.assertEqual(len([m for m in messages if m['role']=='tool']),5)
 def test_25_malformed_model_fallback_safe(self):
  r,_=self.run_agent([({'tool_calls':[self.tool(1)]},{}),({'content':'invent 999 runs'},{}),({'content':'invent 999 runs'},{})]);self.assertEqual(r['status'],'grounded');self.assertNotIn('999',r['text']);self.assertTrue(r['facts'])
 def test_26_provider_failure_not_cached(self):
  with patch('agent.provider',side_effect=RuntimeError('offline')):
   with self.assertRaises(RuntimeError):ask('outage',self.p,self.s,self.model,'RCB','2026-10-18','test-key',self.owner)
  with storage.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM cache').fetchone()[0],0)
 def test_27_session_team_isolation(self):
  a=self.owner;b=storage.scope('second-session','RCB');c=storage.scope('test-session','MI');storage.save(a,'briefs','private',{'team':'RCB'});storage.cache(a,'key',{'secret':'example'});self.assertEqual(len(storage.records(a)),1)
  for other in [b,c]:self.assertEqual(storage.records(other),[]);self.assertIsNone(storage.cached(other,'key'))
  with self.assertRaises(ValueError):storage.records('')
 def test_28_atomic_allowance(self):
  for _ in range(2):storage.reserve_call(self.owner,global_limit=3,session_limit=2)
  with self.assertRaises(RuntimeError):storage.reserve_call(self.owner,global_limit=3,session_limit=2)
  second=storage.scope('second','MI');storage.reserve_call(second,global_limit=3,session_limit=2)
  with self.assertRaises(RuntimeError):storage.reserve_call(storage.scope('third','CSK'),global_limit=3,session_limit=2)
 def test_29_parser_extras_and_wickets(self):
  sample={'info':{'gender':'male','overs':6,'dates':['2020-01-01'],'season':2020,'teams':['A','B'],'players':{'A':['Batter'],'B':['Bowler']},'registry':{'people':{'Batter':'bat','Bowler':'bowl'}}},'innings':[{'team':'A','target':{'overs':6},'powerplays':[{'from':0.1,'to':0.2}], 'overs':[{'over':0,'deliveries':[{'batter':'Batter','bowler':'Bowler','runs':{'batter':0,'total':1},'extras':{'wides':1}},{'batter':'Batter','bowler':'Bowler','runs':{'batter':4,'total':5},'extras':{'noballs':1}},{'batter':'Batter','bowler':'Bowler','runs':{'batter':0,'total':0},'wickets':[{'kind':'run out','player_out':'Batter'}]}]}]}]}
  d=Path(self.temp.name);src=d/'source';src.mkdir()
  with zipfile.ZipFile(src/'ipl_json.zip','w') as z:z.writestr('123.json',json.dumps(sample));z.writestr('1473495.json',json.dumps(sample))
  build(src,d/'output');r=pd.read_csv(d/'output/match_players.csv.gz').set_index('player_id');self.assertEqual(r.loc['bat','balls'],2);self.assertEqual(r.loc['bowl','legal_balls'],1);self.assertEqual(r.loc['bowl','wickets'],0);self.assertEqual(r.loc['bat','dismissals'],1);self.assertEqual(r.loc['bat','pp_balls'],1);self.assertEqual(r.loc['bat','mid_balls'],1)
 def test_30_malformed_provider_protocol(self):
  for msg in ['not-an-object',{'tool_calls':'invalid'},{'tool_calls':[{'id':'x','function':{}},{'id':'x','function':{}}]}]:
   with patch('agent.provider',return_value=(msg,{})):
    with self.assertRaises(RuntimeError):ask('bad protocol',self.p,self.s,self.model,'RCB','2026-10-18','test-key',self.owner)
 def test_31_safe_serialization(self):self.assertEqual(json.dumps(safe({'x':float('nan')}),allow_nan=False),'{"x": null}')

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Release);r=unittest.TextTestRunner(verbosity=2).run(suite);(ROOT/'data/test_results.json').write_text(json.dumps({'tests_run':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'skipped':len(r.skipped),'tests':unittest.defaultTestLoader.getTestCaseNames(Release),'scope':'Offline regression and controlled provider fixtures. No live-provider quality or authentication claim.'},indent=2));sys.exit(not r.wasSuccessful())
