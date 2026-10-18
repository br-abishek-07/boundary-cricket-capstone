"""Chronological IPL probability model; identical feature construction in evaluation and serving."""
from collections import defaultdict
from pathlib import Path
import json,math,re
import numpy as np
import pandas as pd
from scipy.optimize import minimize
ROOT=Path(__file__).resolve().parents[1]

def venue_key(value):
 text=re.sub(r'[^a-z0-9]','',value.lower())
 for token,label in [('chinnaswamy','M Chinnaswamy Stadium, Bengaluru'),('wankhede','Wankhede Stadium, Mumbai'),('eden','Eden Gardens, Kolkata'),('ferozshah','Arun Jaitley Stadium, Delhi'),('arunjaitley','Arun Jaitley Stadium, Delhi'),('narendramodi','Narendra Modi Stadium, Ahmedabad'),('sardarpatel','Narendra Modi Stadium, Ahmedabad'),('chidambaram','MA Chidambaram Stadium, Chennai')]:
  if token in text:return label
 return value.strip()

def initial_state():return {'elo':{},'form':{},'venues':{},'last_date':None}
def sigmoid(x):return 1/(1+np.exp(-np.clip(x,-35,35)))
def features(state,t1,t2,venue='',chasing=None):
 e=state['elo'];f=state['form'];v=state['venues'].get(venue_key(venue),[6.,12.])
 pre=[(e.get(t1,1500)-e.get(t2,1500))/400,f.get(t1,0)-f.get(t2,0)]
 sign=1 if chasing==t1 else (-1 if chasing==t2 else 0)
 return np.array(pre),np.array(pre+[sign,sign*(v[0]/v[1]-.5)*4])
def chase_for(row):return row.toss_winner if row.toss_decision=='field' else (row.team2 if row.toss_winner==row.team1 else row.team1)
def update(state,rows):
 # All matches on a date are forecast before any result from that date updates state.
 delta=defaultdict(float);form_updates=defaultdict(list)
 for row in rows:
  a,b=row.team1,row.team2;y=float(row.winner==a);e=state['elo'];expected=float(sigmoid((e.get(a,1500)-e.get(b,1500))*math.log(10)/400))
  delta[a]+=20*(y-expected);delta[b]-=20*(y-expected);form_updates[a].append(2*y-1);form_updates[b].append(1-2*y)
  chase=chase_for(row);v=state['venues'].setdefault(venue_key(row.venue),[6.,12.]);v[0]+=int(row.winner==chase);v[1]+=1
 for t,d in delta.items():state['elo'][t]=state['elo'].get(t,1500)+d
 for t,ys in form_updates.items():state['form'][t]=.8*state['form'].get(t,0)+.2*float(np.mean(ys))

def chronology(matches):
 m=matches[(matches.competition=='IPL') & matches.winner.isin(matches.team1.tolist()+matches.team2.tolist())].sort_values(['date','match_id'])
 state=initial_state();records=[]
 for date,group in m.groupby('date',sort=True):
  rr=list(group.itertuples())
  for row in rr:
   x,z=features(state,row.team1,row.team2,row.venue,chase_for(row));records.append(dict(match_id=str(row.match_id),date=date,season=str(row.season),y=int(row.winner==row.team1),pre=x.tolist(),post=z.tolist(),elo_baseline=float(sigmoid(x[0]*math.log(10)))))
  update(state,rr);state['last_date']=date
 return records,state

def fit(x,y):
 x=np.array(x);y=np.array(y)
 def objective(w):
  z=x@w;return float(np.logaddexp(0,z).sum()-y@z+2.5*(w@w)), x.T@(sigmoid(z)-y)+5*w
 return minimize(objective,np.zeros(x.shape[1]),jac=True,method='BFGS').x

def metrics(y,p):
 y=np.array(y);p=np.clip(np.array(p),1e-8,1-1e-8);n=len(y)
 if not n:return {}
 acc=float(np.mean((p>=.5)==y));z=1.96;den=1+z*z/n;center=(acc+z*z/(2*n))/den;half=z*np.sqrt(acc*(1-acc)/n+z*z/(4*n*n))/den
 return {'n':n,'accuracy':round(acc,5),'accuracy_95_wilson':[round(center-half,5),round(center+half,5)],'brier':round(float(np.mean((p-y)**2)),6),'log_loss':round(float(np.mean(-y*np.log(p)-(1-y)*np.log(1-p))),6)}

def build(matches):
 records,state=chronology(matches);train=[r for r in records if r['date']<'2023-01-01'];validation=[r for r in records if '2023-01-01'<=r['date']<'2024-01-01'];test=[r for r in records if r['date']>='2024-01-01'];weights={k:fit([r[k] for r in train],[r['y'] for r in train]).tolist() for k in ['pre','post']}
 model={'weights':weights,'state':state,'trained_before':'2023-01-01','validation_year':'2023','test_from':'2024-01-01','version':'boundary-temporal-2'}
 training_rows=matches[(matches.competition=='IPL')&(matches.date<'2023-01-01')&(matches.winner!='')]
 chase_rate=float(np.mean([row.winner==chase_for(row) for row in training_rows.itertuples()]))
 model['training_chase_rate']=chase_rate
 reports={};predictions=[]
 for label,split in [('validation',validation),('test',test)]:
  y=[r['y'] for r in split];reports[label]={}
  for k in ['pre','post']:
   p=[float(sigmoid(np.dot(weights[k],r[k]))) for r in split];reports[label][k]=metrics(y,p)
  reports[label]['constant_50_forecast']=metrics(y,[.5]*len(y));reports[label]['elo']=metrics(y,[r['elo_baseline'] for r in split]);reports[label]['training_chase_baseline']=metrics(y,[chase_rate if r['post'][2]>0 else 1-chase_rate for r in split])
  for r in split:predictions.append({**{k:r[k] for k in ['match_id','date','season','y']},'pre':float(sigmoid(np.dot(weights['pre'],r['pre']))),'post':float(sigmoid(np.dot(weights['post'],r['post']))),'split':label})
 p=pd.DataFrame(predictions);reports['test_by_season']={str(s):{k:metrics(g.y,g[k]) for k in ['pre','post']} for s,g in p[p.split=='test'].groupby('season')}
 reports['calibration']=[]
 for lo in np.arange(0,1,.1):
  g=p[(p.split=='test')&(p.post>=lo)&(p.post<lo+.1)]
  if len(g):reports['calibration'].append({'bin':f'{lo:.1f}–{lo+.1:.1f}','n':len(g),'predicted':float(g.post.mean()),'observed':float(g.y.mean())})
 reports['method']={'training_matches':len(train),'design':'Fixed regularized logistic model trained before 2023; validation 2023; untouched test 2024 onward. Team ratings update after each match date, using past results only.','uncertainty':'Wilson intervals assume independent binary outcomes; season dependence is not captured.','features':'Pre: team Elo and exponential result form. Post: same plus chasing indicator and prior venue chase record. No player-lineup, injury or weather inputs.','selection':'No model selection or tuning on validation/test; fixed regularization and rating constants.','claim':'Research probabilities; no guarantee of predictive advantage. Current ratings use all uploaded IPL history for future scenarios.'}
 reports['gate']={'passed':all(reports[x]['post']['brier']<reports[x]['training_chase_baseline']['brier'] for x in ['validation','test']),'rule':'Research model must beat training-derived chase-rate Brier in validation AND held-out test. Otherwise serve the baseline, not the model.','baseline_chase_rate':chase_rate}
 model['gate_passed']=reports['gate']['passed']
 for name,obj in [('prediction_model.json',model),('prediction_report.json',reports)]: (ROOT/'data'/name).write_text(json.dumps(obj,indent=2))
 p.to_csv(ROOT/'data/prediction_holdout.csv',index=False)
 return reports

def predict(model,t1,t2,venue='',chasing=None):
 if t1==t2:raise ValueError('Select distinct teams.')
 if chasing is not None and chasing not in [t1,t2]:raise ValueError('Chasing team must be a participant.')
 x,z=features(model['state'],t1,t2,venue,chasing);research_pre=float(sigmoid(np.dot(model['weights']['pre'],x)));research_post=float(sigmoid(np.dot(model['weights']['post'],z))) if chasing else None
 baseline=(model['training_chase_rate'] if chasing==t1 else 1-model['training_chase_rate']) if chasing else None
 return {'pre':.5,'post':research_post if model.get('gate_passed') else baseline,'research_pre':research_pre,'research_post':research_post,'method':'Research model' if model.get('gate_passed') else 'Training-derived chase-rate baseline; research model failed acceptance gate','as_of':model['state']['last_date'],'model':model['version'],'unknown_team':t1 not in model['state']['elo'] or t2 not in model['state']['elo'],'gate_passed':model.get('gate_passed',False)}
if __name__=='__main__':
 r=build(pd.read_csv(ROOT/'data/matches.csv.gz',keep_default_na=False,dtype={'match_id':str,'season':str}));print(json.dumps(r['test'],indent=2))
