"""Dated evidence and workload-constrained planning. Scores are explicit heuristics."""
from pathlib import Path
import json,re,unicodedata
import numpy as np
import pandas as pd
from scipy.optimize import Bounds,LinearConstraint,milp
ROOT=Path(__file__).parent
CORRECTIONS={'ce794613':'T Natarajan','2c25d4f5':'Devdutt Padikkal'}
def normal(s):return re.sub(r'[^a-z0-9]','',unicodedata.normalize('NFKD',str(s)).lower())
def load():
 p=pd.read_csv(ROOT/'data/match_players.csv.gz',dtype={'player_id':str,'match_id':str,'season':str});s=pd.read_csv(ROOT/'data/squads.csv');a=pd.read_csv(ROOT/'data/auction.csv',encoding='utf-8-sig')
 # Shared missing-ID sentinels are not identities. Give each unregistered squad row a unique planning ID.
 known=s.cricsheet_id.astype(str).str.fullmatch(r'[0-9a-f]{8}')
 s.loc[~known,'cricsheet_id']=['SQUAD:'+t+':'+normal(n) for t,n in zip(s.loc[~known,'franchise_id'],s.loc[~known,'player_name'])]
 names=p.sort_values('date').drop_duplicates('player_id',keep='last').set_index('player_id').player.to_dict();names.update(s.set_index('cricsheet_id').player_name.to_dict());names.update(CORRECTIONS)
 p['alias']=p.player;p['player']=p.player_id.map(names);p['matches']=1;p['last_date']=p.date;s.player_name=s.cricsheet_id.map(names).fillna(s.player_name)
 return p,s,a

def resolve(players,query):
 if not str(query).strip():return []
 q=normal(query);pairs=players[['player_id','player','alias']].drop_duplicates();pairs['exact']=pairs.player.map(normal).eq(q)|pairs.alias.map(normal).eq(q)|pairs.player_id.eq(query)
 exact=pairs[pairs.exact].drop_duplicates('player_id')
 if len(exact):return exact[['player_id','player']].to_dict('records')
 hits=pairs[pairs.player.map(normal).str.contains(q,regex=False)|pairs.alias.map(normal).str.contains(q,regex=False)].drop_duplicates('player_id')
 return hits[['player_id','player']].head(8).to_dict('records')

def squads_asof(squads,until):
 if pd.Timestamp(until).year<2026:raise ValueError('The supplied roster is a 2026 snapshot. Historical squad reconstruction before 2026 is unavailable.')
 r=squads.copy();events=json.loads((ROOT/'data/squad_events.json').read_text())
 for event in events['events']:
  if event['date']<until:
   mask=r.player_name.eq(event['player']);r.loc[mask,'franchise_id']=event['to'];r.loc[mask,'designation']='Player'
 r['roster_source']='Supplied 2026 snapshot + sourced dated trade events';return r

def window(until,years=3):return (pd.Timestamp(until)-pd.DateOffset(years=years)).date().isoformat()
def select_window(players,competition,since,until,phase):
 if since>=until:raise ValueError('Window start must precede the exclusive cutoff.')
 p=players[(players.date>=since)&(players.date<until)].copy()
 if competition!='ALL':p=p[p.competition==competition]
 if phase!='All':
  pre={'Powerplay':'pp','Middle':'mid','Death':'death'}[phase]
  for target,col in [('runs',pre+'_runs'),('balls',pre+'_balls'),('conceded',pre+'_conceded'),('legal_balls',pre+'_legal'),('wickets',pre+'_wickets'),('dismissals',pre+'_dismissals')]:p[target]=p[col]
 return p

def scout(players,competition='IPL',since=None,min_balls=60,discipline='Batting',until='2026-10-18',phase='All'):
 since=since or window(until);p=select_window(players,competition,since,until,phase);cols=['matches','runs','balls','conceded','legal_balls','wickets','dismissals','pp_legal','mid_legal','death_legal'];keys=['player_id','player']+(['competition'] if competition=='ALL' else [])
 p['weight']=np.exp2(-(pd.Timestamp(until)-pd.to_datetime(p.date)).dt.days/365.)
 for col in ['runs','balls','conceded','legal_balls','wickets','dismissals']:p['weighted_'+col]=p[col]*p.weight
 weighted=['weighted_'+col for col in ['runs','balls','conceded','legal_balls','wickets','dismissals']]
 g=p.groupby(keys,as_index=False)[cols+weighted].sum();sample='balls' if discipline=='Batting' else 'legal_balls';g=g[g[sample]>=min_balls].copy()
 g['strike_rate']=100*g.runs/g.balls.replace(0,np.nan);g['economy']=6*g.conceded/g.legal_balls.replace(0,np.nan);g['reliability']=g['weighted_'+sample]/(g['weighted_'+sample]+120)
 # Separate competition baselines; ALL is grouped, never a league-strength translation.
 group_keys=['competition'] if competition=='ALL' else []
 g['score']=0.
 groups=g.groupby('competition') if group_keys else [('',g)]
 for comp,sub in groups:
  raw=p[p.competition==comp] if group_keys else p
  if discipline=='Batting':
   b=max(raw.weighted_balls.sum(),1);par=raw.weighted_runs.sum()/b;d=raw.weighted_dismissals.sum()/b;score=100*((sub.weighted_runs+120*par)/(sub.weighted_balls+120)-par)-18*100*((sub.weighted_dismissals+120*d)/(sub.weighted_balls+120)-d)
  else:
   b=max(raw.weighted_legal_balls.sum(),1);par=raw.weighted_conceded.sum()/b;w=raw.weighted_wickets.sum()/b;score=6*(par-(sub.weighted_conceded+120*par)/(sub.weighted_legal_balls+120))+12*6*((sub.weighted_wickets+120*w)/(sub.weighted_legal_balls+120)-w)
  g.loc[sub.index,'score']=score
 g=g.sort_values((['competition'] if competition=='ALL' else [])+['score','player_id'],ascending=([True] if competition=='ALL' else [])+[False,True]);return g.round(4)

def roster_scores(players,squads,team,until='2026-10-18',competition='IPL'):
 dated=squads_asof(squads,until);r=dated[dated.franchise_id==team].copy();since=window(until)
 for discipline,col,sample in [('Batting','bat_score','balls'),('Bowling','bowl_score','legal_balls')]:
  scores=scout(players,competition,since,min_balls=1,discipline=discipline,until=until)
  cols=['player_id','score',sample]+(['pp_legal','mid_legal','death_legal'] if discipline=='Bowling' else [])
  r=r.merge(scores[cols].rename(columns={'player_id':'cricsheet_id','score':col}),on='cricsheet_id',how='left')
 r['evidence_missing']=r.bat_score.isna()&r.bowl_score.isna();fill=['bat_score','bowl_score','balls','legal_balls','pp_legal','mid_legal','death_legal'];r[fill]=r[fill].fillna(0)
 r['utility']=r.bat_score/10+r.bowl_score;r['bowling_capacity']=np.where(r.legal_balls>=120,4,0)
 for phase,threshold in [('pp',36),('mid',36),('death',24)]:r[phase+'_capacity']=np.where((r.bowling_capacity>0)&(r[phase+'_legal']>=threshold),4,0)
 # Reference attack types are explicit planning tags; unknown remains unknown.
 tags=json.loads((ROOT/'data/attack_types.json').read_text()) if (ROOT/'data/attack_types.json').exists() else {}
 r['attack_type']=r.player_name.map(tags).fillna('Unknown');return r

def optimize(roster,excluded=(),size=11,max_overseas=4,min_bowlers=5,min_batters=5,costs=None,budget=None,locked=(),min_spin=0,min_pace=0,overrides=None):
 r=roster[~roster.player_name.isin(excluded)].copy().sort_values('cricsheet_id').reset_index(drop=True)
 if len(r)<size:return {'ok':False,'reason':'Fewer than eleven available players.'}
 if not set(locked)<=set(r.player_name):return {'ok':False,'reason':'A locked player is excluded or not in the dated squad.'}
 # Unsupported players are not silently assigned a performance value.
 eligible=~r.evidence_missing
 override_notes=[]
 for name,o in (overrides or {}).items():
  if name not in set(r.player_name):continue
  if not o.get('reason','').strip():return {'ok':False,'reason':'Every capability override needs an analyst justification.'}
  cap=float(o.get('capacity',0))
  if not np.isfinite(cap) or not 0<=cap<=4:return {'ok':False,'reason':'Override bowling capacity must be 0–4 overs.'}
  idx=r.index[r.player_name.eq(name)][0];r.loc[idx,'bowling_capacity']=cap
  for ph in ['pp','mid','death']:
   phase_cap=float(o.get(ph,0))
   if not np.isfinite(phase_cap) or not 0<=phase_cap<=cap:return {'ok':False,'reason':'Phase capability must be finite and between zero and the total overs cap.'}
   r.loc[idx,ph+'_capacity']=phase_cap
  if o.get('attack_type') in ['Spin','Pace']:r.loc[idx,'attack_type']=o['attack_type']
  if r.loc[idx,'evidence_missing']:
   if 'utility' not in o:return {'ok':False,'reason':'An unobserved player needs an explicit scenario utility assumption.'}
   utility=float(o['utility'])
   if not np.isfinite(utility):return {'ok':False,'reason':'Utility assumption must be finite.'}
   r.loc[idx,'utility']=utility;eligible.loc[idx]=True
  override_notes.append({'player':name,**o})
 if sum(eligible)<11:return {'ok':False,'reason':'Insufficient observed players. Add justified scenario assumptions or widen the evidence window.'}
 n=len(r);v=4*n;rows=[];lo=[];hi=[]
 def constraint(x,l,h):rows.append(x);lo.append(l);hi.append(h)
 def on_x(x):return np.concatenate([np.asarray(x,float),np.zeros(3*n)])
 constraint(on_x(np.ones(n)),size,size);constraint(on_x(r.is_overseas),0,max_overseas);constraint(on_x(r.is_wicketkeeper),1,np.inf)
 constraint(on_x((r.bowling_capacity>0).astype(int)),min_bowlers,np.inf);constraint(on_x((r.balls>=30).astype(int)),min_batters,np.inf)
 constraint(on_x((r.attack_type.eq('Spin')&(r.bowling_capacity>0)).astype(int)),min_spin,np.inf);constraint(on_x((r.attack_type.eq('Pace')&(r.bowling_capacity>0)).astype(int)),min_pace,np.inf)
 if budget is not None:
  if not np.isfinite(budget) or budget<0:return {'ok':False,'reason':'Invalid scenario budget.'}
  if costs is None or any(x not in costs for x in r.player_name):return {'ok':False,'reason':'Enter a scenario price for every available player.'}
  prices=np.array([costs[x] for x in r.player_name],float)
  if not np.isfinite(prices).all() or (prices<0).any():return {'ok':False,'reason':'Scenario prices must be nonnegative and complete.'}
  constraint(on_x(prices),0,budget)
 for j,ph in enumerate(['pp','mid','death']):
  a=np.zeros(v);a[n+j*n:n+(j+1)*n]=1;constraint(a,[36,60,24][j],[36,60,24][j])
  for i in range(n):
   a=np.zeros(v);a[i]=-6*r.loc[i,ph+'_capacity'];a[n+j*n+i]=1;constraint(a,-np.inf,0)
 for i in range(n):
  a=np.zeros(v);a[i]=-6*r.loc[i,'bowling_capacity']
  for j in range(3):a[n+j*n+i]=1
  constraint(a,-np.inf,0)
 lower=np.zeros(v);lower[:n]=r.player_name.isin(locked).astype(int);upper=np.concatenate([eligible.astype(int),np.full(3*n,24)])
 objective=np.concatenate([-r.utility.to_numpy()+np.arange(n)*1e-8,np.arange(3*n)*1e-12])
 res=milp(objective,integrality=np.ones(v),bounds=Bounds(lower,upper),constraints=LinearConstraint(np.array(rows),lo,hi),options={'time_limit':10})
 if not res.success:return {'ok':False,'reason':'No supported XI satisfies the roster, evidence, role, phase workload and budget constraints. Inspect coverage or add justified assumptions.'}
 chosen=r[res.x[:n]>.5].copy()
 for j,ph in enumerate(['pp','mid','death']):chosen[ph+'_allocated_balls']=np.rint(res.x[n+j*n:n+(j+1)*n][res.x[:n]>.5]).astype(int)
 if budget is not None:chosen['scenario_cost_cr']=chosen.player_name.map(costs)
 return {'ok':True,'players':chosen,'utility':float(chosen.utility.sum()),'overseas':int(chosen.is_overseas.sum()),'bowlers':int((chosen.bowling_capacity>0).sum()),'keepers':int(chosen.is_wicketkeeper.sum()),'cost':float(chosen.scenario_cost_cr.sum()) if budget is not None else None,'override_notes':override_notes,'scope':'Twenty-over workload plan with 6/10/4 phase allocation. Evidence thresholds and reference styles are planning assumptions, not official rule certification.'}

def player_interval(players,pid,discipline='Batting',until='2026-10-18',since=None,competition='IPL',phase='All'):
 p=select_window(players,competition,since or window(until),until,phase);p=p[p.player_id==pid];sample='balls' if discipline=='Batting' else 'legal_balls';runs='runs' if discipline=='Batting' else 'conceded';scale=100 if discipline=='Batting' else 6;p=p[p[sample]>0]
 if len(p)<5:return {'matches':len(p),'interval':None,'note':'At least five relevant match samples required.'}
 rng=np.random.default_rng(42);idx=rng.integers(0,len(p),(500,len(p)));rate=scale*p[runs].to_numpy()[idx].sum(1)/p[sample].to_numpy()[idx].sum(1)
 return {'matches':len(p),'rate':float(scale*p[runs].sum()/p[sample].sum()),'interval':np.quantile(rate,[.025,.975]).round(2).tolist(),'window':{'since':since or window(until),'until':until,'competition':competition,'phase':phase},'note':'Observed-rate match-bootstrap interval, not future performance; independent-match assumption.'}
