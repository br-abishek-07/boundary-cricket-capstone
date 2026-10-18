"""Reproducible match-level features. All cutoff queries use actual match dates."""
from pathlib import Path
from collections import Counter, defaultdict
import csv,gzip,hashlib,json,zipfile,argparse
LEAGUES={'ipl':'IPL','bbl':'BBL','sma':'SMAT','hnd':'Hundred','t20s':'T20I'}
BOWLER_WICKETS={'bowled','caught','caught and bowled','lbw','stumped','hit wicket'}
DISMISSALS=BOWLER_WICKETS|{'run out','obstructing the field','retired out','hit the ball twice'}
TEAM_MAP={'Chennai Super Kings':'CSK','Mumbai Indians':'MI','Royal Challengers Bangalore':'RCB','Royal Challengers Bengaluru':'RCB','Kolkata Knight Riders':'KKR','Sunrisers Hyderabad':'SRH','Rajasthan Royals':'RR','Gujarat Titans':'GT','Punjab Kings':'PBKS','Kings XI Punjab':'PBKS','Delhi Capitals':'DC','Delhi Daredevils':'DC','Lucknow Super Giants':'LSG'}

def build(source,output):
 out=Path(output);out.mkdir(parents=True,exist_ok=True);all_players=[];matches=[];sources=[];seen=set()
 paths=sorted(p for p in Path(source).rglob('*_json.zip') if p.stem.split('_')[0] in LEAGUES)
 for path in paths:
  league=LEAGUES[path.stem.split('_')[0]];counts=Counter();dates=[]
  with zipfile.ZipFile(path) as archive:
   for name in archive.namelist():
    if not name.endswith('.json'):continue
    d=json.loads(archive.read(name));info=d['info'];mid=Path(name).stem;counts['files']+=1
    if info.get('gender')!='male':counts['excluded_other_gender']+=1;continue
    if league=='IPL' and mid=='1473495':counts['excluded_voided']+=1;continue
    if mid in seen:counts['excluded_duplicate']+=1;continue
    seen.add(mid);date=str(info['dates'][0]);dates.append(date);counts['included']+=1
    reg=info.get('registry',{}).get('people',{});local={}
    def player(name,team=''):
     pid=reg.get(name,league+':'+name)
     if pid not in local:
      local[pid]=dict(match_id=mid,date=date,season=str(info['season']),competition=league,player_id=pid,player=name,team=team,runs=0,balls=0,dismissals=0,conceded=0,legal_balls=0,wickets=0,pp_runs=0,pp_balls=0,mid_runs=0,mid_balls=0,death_runs=0,death_balls=0,pp_conceded=0,pp_legal=0,mid_conceded=0,mid_legal=0,death_conceded=0,death_legal=0,pp_wickets=0,mid_wickets=0,death_wickets=0,pp_dismissals=0,mid_dismissals=0,death_dismissals=0)
     return local[pid]
    for team,names in info.get('players',{}).items():
     for name in names:player(name,team)
    for inn in d.get('innings',[]):
     if inn.get('super_over'):continue
     # Respect innings powerplay metadata, including reduced-overs fractional boundaries.
     planned=int(round(float(inn.get('target',{}).get('overs',info.get('overs',20)))*(5 if league=='Hundred' else 6)))
     death_at=max(0,planned-max(6,round(planned*.2)))
     pp=inn.get('powerplays',[])
     def position(value):
      ov,ball=str(value).split('.') if '.' in str(value) else (str(value),'0')
      return int(ov),int(ball)
     for over in inn.get('overs',[]):
      legal_in_over=0
      for di,dl in enumerate(over.get('deliveries',[]),1):
       loc=(over['over'],di); is_pp=any(position(v['from'])<=loc<=position(v['to']) for v in pp) if pp else over['over']<(5 if league=='Hundred' else min(6,round(planned/6*.3)))
       phase='pp' if is_pp else ('death' if over['over']*(5 if league=='Hundred' else 6)+legal_in_over>=death_at else 'mid')
       bat=player(dl['batter'],inn['team']);bowl=player(dl['bowler']);ex=dl.get('extras',{});faced=int('wides' not in ex);legal=int('wides' not in ex and 'noballs' not in ex)
       runs=int(dl['runs']['batter']);conceded=runs+int(ex.get('wides',0))+int(ex.get('noballs',0))
       bat['runs']+=runs;bat['balls']+=faced;bat[phase+'_runs']+=runs;bat[phase+'_balls']+=faced
       bowl['conceded']+=conceded;bowl['legal_balls']+=legal;bowl[phase+'_conceded']+=conceded;bowl[phase+'_legal']+=legal;legal_in_over+=legal
       for w in dl.get('wickets',[]):
        bowl['wickets']+=int(w['kind'] in BOWLER_WICKETS);bowl[phase+'_wickets']+=int(w['kind'] in BOWLER_WICKETS)
        if w['kind'] in DISMISSALS:
         out_player=player(w['player_out']);out_player['dismissals']+=1;out_player[phase+'_dismissals']+=1
    all_players.extend(local.values())
    teams=info.get('teams',[]);winner=info.get('outcome',{}).get('winner') or info.get('outcome',{}).get('eliminator','')
    if len(teams)==2:
     matches.append(dict(match_id=mid,date=date,season=str(info['season']),competition=league,team1=TEAM_MAP.get(teams[0],teams[0]),team2=TEAM_MAP.get(teams[1],teams[1]),winner=TEAM_MAP.get(winner,winner),venue=info.get('venue','Unknown'),toss_winner=TEAM_MAP.get(info.get('toss',{}).get('winner',''),info.get('toss',{}).get('winner','')),toss_decision=info.get('toss',{}).get('decision','')))
  sources.append(dict(file=path.name,competition=league,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),earliest=min(dates),latest=max(dates),**counts))
 for filename,rows in [('match_players.csv.gz',all_players),('matches.csv.gz',matches)]:
  with gzip.open(out/filename,'wt',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 (out/'audit.json').write_text(json.dumps({'sources':sources,'match_player_rows':len(all_players),'matches':len(matches),'notes':['Men only; voided IPL match 1473495 and duplicate match IDs excluded.','As-of queries include matches strictly earlier than the selected cutoff date.','Powerplay follows recorded innings metadata. Death is a documented analytical final-fifth window of scheduled innings, after the powerplay; not an official field restriction.','Hundred uses five-ball over groups; rates normalized per six legal balls. Missing powerplay metadata uses a labeled proportional fallback.','Squad snapshot and auction source need independent verification.']},indent=2))
 print('Built',len(matches),'matches;',len(all_players),'match-player records')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',default='data');a=p.parse_args();build(a.source,a.output)
