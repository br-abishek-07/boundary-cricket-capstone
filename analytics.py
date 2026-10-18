from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import Bounds,LinearConstraint,milp
ROOT=Path(__file__).parent

def load():
 p=pd.read_csv(ROOT/'data/match_players.csv.gz',dtype={'player_id':str,'match_id':str,'season':str});s=pd.read_csv(ROOT/'data/squads.csv');a=pd.read_csv(ROOT/'data/auction.csv',encoding='utf-8-sig')
 canonical=p.sort_values('date').drop_duplicates('player_id').set_index('player_id').player.to_dict();canonical.update(s.set_index('cricsheet_id').player_name.to_dict());p.player=p.player_id.map(canonical);p['last_date']=p.date;p['matches']=1
 return p,s,a

def scout(players,competition='ALL',since='2024-01-01',min_balls=60,discipline='Batting',until='2100-01-01',phase='All'):
 p=players[(players.date>=since)&(players.date<until)].copy()
 if competition!='ALL':p=p[p.competition==competition]
 if phase!='All':
  prefix={'Powerplay':'pp','Middle':'mid','Death':'death'}[phase]
  for target,col in [('runs',prefix+'_runs'),('balls',prefix+'_balls'),('conceded',prefix+'_conceded'),('legal_balls',prefix+'_legal')]:p[target]=p[col]
 cols=['matches','runs','balls','conceded','legal_balls','wickets','dismissals','death_balls','death_runs','death_legal','death_conceded']
 g=p.groupby(['player_id','player'],as_index=False)[cols].sum()
 batting=discipline=='Batting';sample='balls' if batting else 'legal_balls';g=g[g[sample]>=min_balls].copy()
 # Schema is stable even for an empty shortlist.
 baseline=p.runs.sum()/max(p.balls.sum(),1) if batting else p.conceded.sum()/max(p.legal_balls.sum(),1)
 g['strike_rate']=100*g.runs/g.balls.replace(0,np.nan);g['economy']=6*g.conceded/g.legal_balls.replace(0,np.nan)
 g['reliability']=g[sample]/(g[sample]+120)
 rate=(g.runs+120*baseline)/(g.balls+120) if batting else (g.conceded+120*baseline)/(g.legal_balls+120)
 g['score']=100*(rate-baseline) if batting else 6*(baseline-rate)
 g['death_economy']=6*g.death_conceded/g.death_legal.replace(0,np.nan)
 if phase!='All':g=g.drop(columns=['wickets','dismissals']) # whole-match wickets cannot be attributed to a selected phase
 return g.sort_values(['score','player_id'],ascending=[False,True]).round(3)

def roster_scores(players,squads,team,until='2100-01-01'):
 r=squads[squads.franchise_id==team].copy()
 for discipline,col,sample in [('Batting','bat_score','balls'),('Bowling','bowl_score','legal_balls')]:
  scores=scout(players,since='2024-01-01',min_balls=1,discipline=discipline,until=until)
  r=r.merge(scores[['player_id','score',sample]].rename(columns={'player_id':'cricsheet_id','score':col}),on='cricsheet_id',how='left')
 r['evidence_missing']=r.bat_score.isna() & r.bowl_score.isna();r[['bat_score','bowl_score','balls','legal_balls']]=r[['bat_score','bowl_score','balls','legal_balls']].fillna(0)
 bat=r.role.isin(['Batter','Wicket Keeper','All Rounder']);bowl=r.role.isin(['Bowler','All Rounder']);r['utility']=r.bat_score/10*bat+r.bowl_score*bowl;r.loc[r.evidence_missing,'utility']=-1
 return r

def optimize(roster,excluded=(),size=11,max_overseas=4,min_bowlers=5,min_batters=5,costs=None,budget=None,locked=()):
 r=roster[~roster.player_name.isin(excluded)].copy().reset_index(drop=True)
 if len(r)<size:return {'ok':False,'reason':'Not enough available players.'}
 if not set(locked)<=set(r.player_name):return {'ok':False,'reason':'A locked player is excluded or missing.'}
 a=[np.ones(len(r)),r.is_overseas,r.is_wicketkeeper,r.role.isin(['Bowler','All Rounder']).astype(int),r.role.isin(['Batter','Wicket Keeper','All Rounder']).astype(int)];low=[size,0,1,min_bowlers,min_batters];high=[size,max_overseas,np.inf,np.inf,np.inf]
 if budget is not None:
  if costs is None or any(n not in costs for n in r.player_name):return {'ok':False,'reason':'Provide a scenario price for every available player.'}
  c=np.array([costs[n] for n in r.player_name],float)
  if not np.isfinite(c).all() or (c<0).any():return {'ok':False,'reason':'Scenario prices must be finite and nonnegative.'}
  a.append(c);low.append(0);high.append(float(budget))
 res=milp(-r.utility.to_numpy(),integrality=np.ones(len(r)),bounds=Bounds(r.player_name.isin(locked).astype(int),1),constraints=LinearConstraint(np.array(a,float),low,high),options={'time_limit':10})
 if not res.success:return {'ok':False,'reason':'No verified optimum. The constraints may be infeasible or the solver timed out.'}
 chosen=r[res.x>.5].copy()
 if budget is not None:chosen['scenario_cost_cr']=chosen.player_name.map(costs)
 return {'ok':True,'players':chosen,'utility':float(chosen.utility.sum()),'overseas':int(chosen.is_overseas.sum()),'bowlers':int(chosen.role.isin(['Bowler','All Rounder']).sum()),'keepers':int(chosen.is_wicketkeeper.sum()),'cost':float(chosen.scenario_cost_cr.sum()) if budget is not None else None}

def player_interval(players,pid,discipline='Batting',until='2100-01-01'):
 p=players[(players.player_id==pid)&(players.date<until)];sample='balls' if discipline=='Batting' else 'legal_balls';runs='runs' if discipline=='Batting' else 'conceded';scale=100 if discipline=='Batting' else 6;p=p[p[sample]>0]
 if len(p)<5:return {'matches':len(p),'interval':None,'note':'At least five match samples required.'}
 rng=np.random.default_rng(42);idx=rng.integers(0,len(p),(400,len(p)));samples=scale*p[runs].to_numpy()[idx].sum(1)/p[sample].to_numpy()[idx].sum(1)
 return {'matches':len(p),'rate':float(scale*p[runs].sum()/p[sample].sum()),'interval':np.quantile(samples,[.025,.975]).round(2).tolist(),'note':'95% match-bootstrap interval for observed pooled rate; not future performance. Independent-match assumption.'}

def evidence(players,squads,question,team):
 bat=scout(players,min_balls=120);bowl=scout(players,min_balls=120,discipline='Bowling');names=players[['player_id','player']].drop_duplicates();q=question.lower();matches=names[names.player.str.lower().map(lambda n:len(n)>3 and n in q)].head(5)
 dossiers=players[players.player_id.isin(matches.player_id)].sort_values('date',ascending=False).head(12);result=optimize(roster_scores(players,squads,team))
 return {'sources':{'S1':'Uploaded Cricsheet match records; data/audit.json','S2':'Original supplied squad snapshot; unverified current availability'},'selected_team':team,'batting_candidates':bat.head(5).to_dict('records'),'bowling_candidates':bowl.head(5).to_dict('records'),'matched_recent_matches':dossiers[['player','date','competition','runs','balls','wickets','legal_balls']].to_dict('records'),'suggested_XI':result['players'][['player_name','role','utility','evidence_missing']].to_dict('records') if result['ok'] else result,'limitations':['Scores are descriptive heuristics, not player forecasts or auction values.','Mixed competitions are not strength-adjusted.','Current availability and prices are not verified.','Lineup constraints are explicit planning assumptions, not exhaustive official certification.']}
