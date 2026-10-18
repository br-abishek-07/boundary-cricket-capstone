"""Boundary — one integrated capstone release."""
import datetime,html,json,os,tomllib
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import streamlit as st
from analytics import load,scout,roster_scores,optimize,player_interval
from prediction import predict
from agent import ask,demonstration,safe,provider
import storage
ROOT=Path(__file__).parent
st.set_page_config(page_title='Boundary · Franchise research',page_icon='◉',layout='wide',initial_sidebar_state='auto')
st.markdown('''<style>
.block-container{padding:2.7rem 3rem;max-width:1460px}h1{font-family:Georgia,'Times New Roman',serif;font-size:3.4rem!important;line-height:1.05!important;letter-spacing:-1.8px;font-weight:500!important;margin-bottom:1rem!important}h2,h3{letter-spacing:-.6px} [data-testid="stSidebar"]{border-right:1px solid #d9ddd5;background:#edf0e8} .eyebrow{font-size:10px;letter-spacing:2.6px;color:#176b55;font-weight:700;margin-bottom:14px}.intro{font-size:17px;line-height:1.65;color:#586969;max-width:760px;margin:0 0 25px}.folio{display:flex;justify-content:space-between;border-bottom:1px solid #ccd3c9;padding-bottom:15px;margin-bottom:28px;font-size:10px;letter-spacing:1.6px;color:#5e6d63}.research-note{border-left:3px solid #b08742;padding:9px 16px;background:#f1eee4;font-size:13px;line-height:1.6;color:#595944;margin:12px 0 25px} div[data-testid="stMetric"]{border-top:2px solid #176b55;padding-top:12px} [data-testid="stMetricValue"]{font-family:Georgia,serif}button{border-radius:4px!important}.stCaption{line-height:1.65} @media(max-width:700px){.block-container{padding:4.2rem 1rem}h1{font-size:2.5rem!important}}
</style>''',unsafe_allow_html=True)
@st.cache_data
def data():return load()
p,s,a=data();audit=json.loads((ROOT/'data/audit.json').read_text());model=json.loads((ROOT/'data/prediction_model.json').read_text());report=json.loads((ROOT/'data/prediction_report.json').read_text())
def key():
 if st.session_state.get('private_key'):return st.session_state.private_key
 if os.getenv('DEEPSEEK_API_KEY'):return os.getenv('DEEPSEEK_API_KEY')
 secret=ROOT/'.streamlit/secrets.toml'
 if secret.exists():return tomllib.loads(secret.read_text()).get('DEEPSEEK_API_KEY','')
 try:return st.secrets.get('DEEPSEEK_API_KEY','')
 except FileNotFoundError:return ''
def table(frame,**kw):st.dataframe(frame,hide_index=True,width='stretch',**kw)
def download(frame,name):st.download_button('Export CSV',frame.to_csv(index=False),file_name=name,mime='text/csv')
def heading(title,description):
 title_html=html.escape(title).replace('\n','<br>')
 st.markdown(f'<h1 style="font-family:Georgia,serif;font-size:3.4rem;font-weight:400;line-height:1.08;letter-spacing:-1.8px;margin:0 0 22px">{title_html}</h1><div class="intro">{html.escape(description)}</div>',unsafe_allow_html=True)
def note(text):st.markdown(f'<div class="research-note">{html.escape(text)}</div>',unsafe_allow_html=True)
with st.sidebar:
 st.markdown('## BOUNDARY');st.caption('FRANCHISE RESEARCH STUDIO')
 st.divider();team=st.selectbox('Franchise desk',sorted(s.franchise_id.unique()),index=7)
 page=st.radio('Workspace',['Decision desk','Scouting & comparison','Squad & auction scenarios','Player dossier','Match research','Decision journal','Evaluation & SWOT','Settings'])
 st.divider();today=datetime.datetime.now(ZoneInfo('Asia/Kolkata')).date();cutoff=st.date_input('Use matches before',value=today,min_value=datetime.date(2008,1,1),max_value=today+datetime.timedelta(days=365));until=cutoff.isoformat()
 st.caption('Historical squad membership is not reconstructed. The supplied squad snapshot remains fixed when you change the match cutoff.')
 st.caption('CAPSTONE · INTEGRATED RELEASE\n\nDeepSeek: '+('private key configured' if key() else 'key required for live analysis'))
st.markdown(f'<div class="folio"><span>BOUNDARY / RESEARCH EDITION</span><span>{html.escape(team)} DESK · DATA BEFORE {until}</span></div>',unsafe_allow_html=True)
if page=='Decision desk':
 heading('Make the next decision\nwith evidence.','Find a role fit, test a replacement, or investigate a matchup. Your analyst works with local tools and leaves a trace of the evidence used.')
 left,right=st.columns([1.8,1],gap='large')
 with left:
  st.subheader('Brief the analyst')
  mode=st.radio('Briefing mode',['Live DeepSeek','Saved demonstration'],horizontal=True,index=0 if key() else 1)
  q=st.text_area('What decision are you making?',value=f'Find death-bowling options for {team}. Compare evidence and explain what remains unknown.',height=110,max_chars=2000)
  st.caption('The analyst retrieves evidence before writing. Inspect the sources and assumptions beside each saved brief.')
  if st.button('Prepare brief',type='primary'):
   try:
    with st.spinner('Researching the decision…'):
     st.session_state.brief=ask(q,p,s,model,team,until,key()) if mode=='Live DeepSeek' else {'text':demonstration(),'mode':'Saved demonstration','trace':[],'team':team,'until':until,'question':q}
    st.session_state.brief['question']=q
   except (ValueError,RuntimeError) as ex:st.error(str(ex))
  if 'brief' in st.session_state:
   brief=st.session_state.brief;st.caption(f"{brief['mode']} · {brief['team']} · cutoff {brief['until']}"+(' · cached' if brief.get('cached') else ''))
   if brief['team']!=team or brief['until']!=until:st.warning('This saved response uses a different team or cutoff. Prepare a new brief to apply the current selection.')
   st.markdown(brief['text'])
   if brief.get('citations_present') is False:st.warning('Source markers are missing. Verify factual claims before using this brief.')
   x,y=st.columns(2);x.download_button('Download brief',brief['text'],'boundary-brief.md')
   if y.button('Save to journal'):storage.save('briefs',brief['question'][:100],safe(brief));st.success('Saved locally with evidence and settings.')
   with st.expander('Tool calls, evidence and token usage'):st.json({k:brief.get(k) for k in ['trace','usage','cached']})
 with right:
  st.subheader('The evidence base')
  for src in audit['sources']:
   st.markdown(f"**{src['competition']}** / {src['included']:,} men’s matches");st.caption(f"{src['earliest']} — {src['latest']}")
  note('Current availability and market prices require verification. Scores describe historical evidence; a recommendation remains a human decision.')
elif page=='Scouting & comparison':
 heading('Find the role.\nThen find the player.','Filter the evidence before ranking it. Compare candidates on sample size, phase performance and uncertainty.')
 c=st.columns(4);league=c[0].selectbox('Competition',['IPL','ALL','BBL','SMAT','Hundred','T20I']);discipline=c[1].selectbox('Discipline',['Batting','Bowling']);phase=c[2].selectbox('Phase',['All','Powerplay','Middle','Death']);sample=c[3].number_input('Minimum relevant balls',min_value=1,max_value=2000,value=120,step=30)
 since=st.selectbox('Window starts',['2024-01-01','2022-01-01','2008-01-01']);ranked=scout(p,league,since,int(sample),discipline,until,phase)
 search=st.text_input('Search within shortlist')
 if search:ranked=ranked[ranked.player.str.contains(search,case=False,regex=False)]
 display=['player','score','reliability','runs','balls','strike_rate','legal_balls','economy','death_economy'];display=[x for x in display if x in ranked]
 table(ranked[display],column_config={'reliability':st.column_config.ProgressColumn('Sample weight',min_value=0,max_value=1,format='%.2f'),'score':st.column_config.NumberColumn('Descriptive score',format='%.2f')});download(ranked,'scouting-shortlist.csv')
 note('Score measures shrunk performance relative to the selected pool: batting per 100 balls, bowling per six balls. Sample weight is not a confidence probability. Combined leagues are not strength-adjusted. Phase wickets are omitted because they are not attributed in this shortlist.')
 st.subheader('Side-by-side evidence')
 names=ranked.player.tolist();chosen=st.multiselect('Compare up to three',names,default=names[:2],max_selections=3)
 if chosen:
  table(ranked[ranked.player.isin(chosen)][display].set_index('player').T.reset_index(names='Measure'))
  st.bar_chart(ranked[ranked.player.isin(chosen)].set_index('player')[['score']],color='#176b55')
  for row in ranked[ranked.player.isin(chosen)].itertuples():
   interval=player_interval(p[(p.competition==league) if league!='ALL' else p.competition.notna()],row.player_id,discipline,until)
   st.caption(f"{row.player}: whole-career selected-competition observed-rate interval {interval.get('interval')} ({interval['matches']} match samples). This interval uses all phases and all dates before cutoff; it does not describe the filtered score.")
elif page=='Squad & auction scenarios':
 heading('Build a feasible plan.\nKeep an alternative.','Exact XI optimization with explicit roles, availability, locked selections and optional scenario costs.')
 roster=roster_scores(p,s,team,until);c=st.columns(2);excluded=c[0].multiselect('Unavailable / exclude',roster.player_name.tolist());locked=c[1].multiselect('Must include',roster.player_name.tolist())
 c=st.columns(3);min_bowl=c[0].slider('Minimum bowling options',4,7,5);min_bat=c[1].slider('Minimum batting options',4,7,5);use_budget=c[2].checkbox('Apply a scenario budget')
 costs=None;budget=None
 if use_budget:
  st.caption('Enter your own prices in crore. Defaults are ₹1 Cr placeholders, not valuations or actual salaries. Budget applies only to the selected XI, not an entire auction squad.')
  budget=st.number_input('XI scenario budget (₹ Cr)',min_value=0.,max_value=500.,value=30.,step=1.)
  costframe=st.data_editor(pd.DataFrame({'Player':roster.player_name,'Scenario cost (₹ Cr)':1.}),hide_index=True,disabled=['Player'],column_config={'Scenario cost (₹ Cr)':st.column_config.NumberColumn(min_value=0.,max_value=100.,step=.1)},key=f'costs_{team}');costs=dict(zip(costframe.Player,costframe['Scenario cost (₹ Cr)']))
 result=optimize(roster,excluded,min_bowlers=min_bowl,min_batters=min_bat,costs=costs,budget=budget,locked=locked)
 if result['ok']:
  c=st.columns(4);c[0].metric('Players',11);c[1].metric('Overseas',f"{result['overseas']} / 4");c[2].metric('Bowling options',result['bowlers']);c[3].metric('Scenario cost',f"₹{result['cost']:.1f} Cr" if result['cost'] is not None else 'Not applied')
  cols=['player_name','role','nationality','utility','balls','legal_balls','evidence_missing']+(['scenario_cost_cr'] if budget is not None else []);table(result['players'][cols]);download(result['players'][cols],'scenario-XI.csv')
  payload=safe({'team':team,'until':until,'excluded':excluded,'locked':locked,'budget':budget,'costs':costs,'min_bowlers':min_bowl,'min_batters':min_bat,'players':result['players'][cols].to_dict('records'),'utility':result['utility']})
  if st.button('Save scenario to journal'):storage.save('briefs',f'{team} XI scenario',payload);st.success('Scenario saved.')
 else:st.warning(result['reason'])
 with st.expander('Full roster and objective'):
  table(roster[['player_name','role','bat_score','bowl_score','utility','evidence_missing']]);st.write('Utility: batting score/10 for batting roles + bowling score for bowling roles. All-rounders count toward both. Missing evidence receives −1 utility. The captain is not forced. These are transparent planning weights, not trained future player values. No Impact Player rule certification is claimed.')
elif page=='Player dossier':
 heading('A career is more\nthan one number.','Read match evidence, seasonal trends and sample uncertainty before making a scouting judgment.')
 names=p[['player_id','player']].drop_duplicates().sort_values('player');label=names.player+' · '+names.player_id;selected=st.selectbox('Player',label.tolist());pid=selected.rsplit(' · ',1)[1];view=p[(p.player_id==pid)&(p.date<until)].copy()
 c=st.columns(3);c[0].metric('Runs',int(view.runs.sum()));c[1].metric('Wickets',int(view.wickets.sum()));c[2].metric('Named appearances',len(view))
 seasons=view.groupby(['competition','season'],as_index=False)[['runs','balls','legal_balls','conceded','wickets']].sum();seasons['strike_rate']=100*seasons.runs/seasons.balls.replace(0,float('nan'));seasons['economy']=6*seasons.conceded/seasons.legal_balls.replace(0,float('nan'));table(seasons)
 if len(seasons):st.bar_chart(seasons.assign(label=seasons.season+' / '+seasons.competition).set_index('label')[['runs']],color='#176b55')
 c=st.columns(2)
 for col,d in zip(c,['Batting','Bowling']):
  interval=player_interval(p,pid,d,until);col.markdown('**'+d+' observed-rate uncertainty**');col.json(interval)
 with st.expander('Match records'):table(view[['date','competition','team','runs','balls','wickets','legal_balls','conceded']].sort_values('date',ascending=False))
 st.subheader('Historical auction evidence');st.caption('2013–2022 supplied records. Name search is literal and approximate; amounts are raw source values, with units and transaction types unverified. This is not a current valuation.')
 query=st.text_input('Auction player name',value=selected.split(' · ')[0].split()[-1]);table(a[a.Player.str.contains(query,case=False,regex=False)])
elif page=='Match research':
 heading('Probabilities,\nwith their evidence.','A chronological IPL model using prior team ratings, form and venue chase history. The evaluated pipeline also serves the scenario forecast.')
 c=st.columns(2);teams=sorted(s.franchise_id.unique());t1=c[0].selectbox('Team A',teams,index=7);t2=c[1].selectbox('Team B',teams,index=0);venue=st.selectbox('Venue',sorted(model['state']['venues']));chasing=st.selectbox('Chasing team',['Unknown',t1,t2])
 if until<=model['state']['last_date']:st.info('The current model snapshot contains later matches than this cutoff. Inspect historical holdouts below; live scenario forecasting is disabled for this date.')
 elif t1==t2:st.warning('Choose distinct teams.')
 else:
  pr=predict(model,t1,t2,venue,None if chasing=='Unknown' else chasing);c=st.columns(2);c[0].metric(f'Pre-toss · {t1}',f"{pr['pre']:.1%}");c[1].metric(f'Post-toss · {t1}',f"{pr['post']:.1%}" if pr['post'] is not None else 'Choose chasing team');st.caption('Rating snapshot: '+pr['as_of']+'. These probabilities do not incorporate player availability, selected XI, weather or pitch reports.')
 st.subheader('Untouched test / 2024–2026');table(pd.DataFrame(report['test']).T.reset_index(names='Forecast'))
 note('Post-toss accuracy is 54.9% on 215 matches; the 95% Wilson interval is 48.2–61.4%. The interval includes chance. A constant 50% forecast has Brier 0.25; its displayed classification accuracy uses the deterministic Team A tie-break, not a random coin flip.')
 st.subheader('Calibration');cal=pd.DataFrame(report['calibration']);table(cal);st.line_chart(cal.set_index('bin')[['predicted','observed']])
 with st.expander('Validation, per-season results and methodology'):st.json(report)
 holdout=pd.read_csv(ROOT/'data/prediction_holdout.csv');download(holdout,'historical-predictions.csv')
elif page=='Decision journal':
 heading('Keep the reasoning.\nReview the outcome.','Saved briefs preserve evidence and scenario settings. Storage is local to this installation; export important work before redeployment.')
 rows=storage.records()
 if not rows:st.info('Save an analyst brief or XI scenario to begin the journal.')
 else:
  for row in rows:
   with st.expander(f"{row['id']:03d} · {row['title']} · {row['created'][:10]}"):
    if 'text' in row['payload']:st.markdown(row['payload']['text'])
    st.json(row['payload'])
  st.download_button('Export complete journal',json.dumps(rows,indent=2),'decision-journal.json')
elif page=='Evaluation & SWOT':
 heading('Make the claims\nreviewable.','Quantitative checks, honest research performance, qualitative review and the product strategy in one place.')
 tabs=st.tabs(['Quantitative','Qualitative','SWOT & architecture','Data provenance'])
 with tabs[0]:
  tests=ROOT/'data/test_results.json'
  if tests.exists():st.json(json.loads(tests.read_text()))
  else:st.info('Run python tests/test_core.py to generate actual results.')
  st.caption('Automated checks do not establish expert usefulness or live model factuality. No pass status is inferred for tests that have not run.')
  st.json(report['test']);st.write('Live DeepSeek evaluation status: network access to api.deepseek.com is blocked by this build environment’s destination policy. Configure that destination in the hosting environment to perform a live check. Offline provider mocks verify tool orchestration and failure handling.')
 with tabs[1]:
  st.write('Record real reviews. No expert scores are prefilled as results. Suggested tasks: compare two bowlers; handle an unknown player; explain a weak sample; report an infeasible XI; reject unsupported current-price claims.')
  with st.form('review'):
   reviewer=st.text_input('Reviewer name or alias');task=st.text_area('Task and response evaluated');ratings={k:st.slider(k,1,5,3) for k in ['Evidence support','Cricket relevance','Tradeoff clarity','Usability','Appropriate uncertainty']};comments=st.text_area('Observations / failure examples');submit=st.form_submit_button('Submit review')
   if submit:
    if not reviewer.strip() or not task.strip():st.error('Enter a reviewer and the task before submitting.')
    else:storage.save('reviews',reviewer,{'task':task,'ratings':ratings,'comments':comments});st.success('Real review saved.')
  reviews=storage.records('reviews')
  if reviews:
   table(pd.DataFrame([{'reviewer':x['title'],'task':x['payload']['task'],**x['payload']['ratings']} for x in reviews]));st.download_button('Export reviews',json.dumps(reviews,indent=2),'qualitative-reviews.json')
  else:st.info('No reviews submitted. Qualitative usefulness remains unvalidated.')
 with tabs[2]:
  table(pd.DataFrame({'Strengths':['Uploaded multi-league history','Exact planning solver','Traceable local tools'],'Weaknesses':['Heuristic scouting weights','Old auction records','No verified live availability'],'Opportunities':['Historical scouting validation','Expert-guided role models','More current squad evidence'],'Threats':['Stale inputs and identity aliases','Overconfident language','Public API cost and data rights']}))
  st.code('Match archives → dated evidence → scouting / optimization / forecast tools\n                                    ↓\n                         DeepSeek selects approved tools\n                                    ↓\n                         cited brief → human review → journal',language=None)
  st.write('Reliability: strict cutoffs, typed tool validation, solver feasibility, global local-installation call allowance, caching and explicit outages. Intelligence: tool choice and evidence synthesis. Predictability: repeatable numerical tools, cached repeated briefs and documented model inputs. AI wording can vary. These controls reduce risk; they do not prove every recommendation correct.')
 with tabs[3]:
  table(pd.DataFrame(audit['sources']));st.caption(f"{audit['match_player_rows']:,} named player-match records / {audit['matches']:,} matches")
  for n in audit['notes']:st.write('• '+n)
  st.download_button('Download provenance',json.dumps(audit,indent=2),'data-audit.json')
else:
 heading('Private configuration.\nClear operating limits.','DeepSeek is a server-side integration. Credentials are excluded from source archives, exports and the journal.')
 st.success('DeepSeek key configured privately.' if key() else 'DeepSeek key is not configured.')
 newkey=st.text_input('Replace key for this session',type='password',placeholder='Enter only if replacing the configured key')
 if st.button('Use session key'):
  if newkey.startswith('sk-') and len(newkey)>12:st.session_state.private_key=newkey;st.success('Session key updated; not written to source or journal.')
  else:st.error('Enter a valid provider key.')
 if st.button('Test provider connection'):
  if not key():st.error('Configure a key first.')
  else:
   try:
    with st.spinner('Checking provider…'):msg,usage=provider([{'role':'user','content':'Reply with OK only.'}],key())
    st.success('Provider responded.');st.json({'usage':usage})
   except RuntimeError as ex:st.error(str(ex))
 st.write('One local SQLite ledger limits this installation to thirty provider calls per UTC day. Each brief uses at most three requests, each with at most 1,100 output tokens. A separate server replica has its own ledger. These are operational limits, not a guaranteed rupee spending cap. Public deployment should add authentication and provider billing controls.')
 st.caption('The key you previously supplied is configured in this runnable workspace only. Rotate it before publishing because it was shared in chat. Deployment packages intentionally contain a secret template; hosting secrets must be configured separately.')
