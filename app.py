import datetime,hashlib,html,json,os,secrets,tomllib
from pathlib import Path
from zoneinfo import ZoneInfo
import altair as alt
import pandas as pd
import streamlit as st
from analytics import load,scout,roster_scores,optimize,player_interval,resolve,squads_asof,window,select_window
from prediction import predict
from agent import ask,dispatch,fact_rows,render,safe,provider
import storage,branding
ROOT=Path(__file__).parent
st.set_page_config(page_title='Boundary · Franchise intelligence',page_icon='🏏',layout='wide',initial_sidebar_state='auto')
@st.cache_resource
def data(signature):return load()
signature=tuple((ROOT/'data'/f).stat().st_mtime_ns for f in ['match_players.csv.gz','squads.csv','squad_events.json']);p,s,a=data(signature)
audit=json.loads((ROOT/'data/audit.json').read_text());model=json.loads((ROOT/'data/prediction_model.json').read_text());report=json.loads((ROOT/'data/prediction_report.json').read_text())
if 'private_session' not in st.session_state:st.session_state.private_session=secrets.token_urlsafe(32)
if 'scenarios' not in st.session_state:st.session_state.scenarios={}
if 'filters' not in st.session_state:st.session_state.filters={'competition':'IPL','discipline':'Bowling','phase':'Death','min_balls':120}
def key():
 if st.session_state.get('private_key'):return st.session_state.private_key
 if os.getenv('DEEPSEEK_API_KEY'):return os.getenv('DEEPSEEK_API_KEY')
 local=ROOT/'.streamlit/secrets.toml'
 if local.exists():return tomllib.loads(local.read_text()).get('DEEPSEEK_API_KEY','')
 try:return st.secrets.get('DEEPSEEK_API_KEY','')
 except FileNotFoundError:return ''
with st.sidebar:
 st.markdown('## BOUNDARY');st.caption('IPL FRANCHISE RESEARCH STUDIO')
 st.markdown(f'<img src="{branding.logo("IPL")}" width="72" alt="Indian Premier League text mark" style="background:#fff;padding:10px;border-radius:5px;margin-bottom:14px">',unsafe_allow_html=True)
 def keep_theme():
  if st.session_state.appearance is None:st.session_state.appearance=st.session_state.get('last_theme','Dark')
  else:st.session_state.last_theme=st.session_state.appearance
 theme=st.segmented_control('Appearance',['Light','Dark'],default=None if 'appearance' in st.session_state else 'Dark',key='appearance',on_change=keep_theme)
 team=st.selectbox('Franchise desk',list(branding.TEAMS),index=7)
 page=st.radio('Workspace',['Decision desk','Scouting & comparison','Squad & auction scenarios','Player dossier','Match research','Decision journal','Evaluation & sources','Settings'])
 today=datetime.datetime.now(ZoneInfo('Asia/Kolkata')).date();cutoff=st.date_input('Use matches before',value=today,min_value=datetime.date(2008,1,1),max_value=today+datetime.timedelta(days=365));until=cutoff.isoformat()
 st.caption('Your journal is private to this browser session and team. Export before closing. No account authentication is configured for this public capstone.')
 if st.button('Start a fresh private session'):st.session_state.private_session=secrets.token_urlsafe(32);st.session_state.pop('brief',None);st.rerun()
style,palette=branding.css(team,theme or 'Light');st.markdown(style,unsafe_allow_html=True);owner=storage.scope(st.session_state.private_session,team);quota_owner=storage.scope(st.session_state.private_session,'__all_teams__')
st.markdown(f'<div class="folio"><span>BOUNDARY / EVIDENCE & DECISIONS</span><span>{team} · {theme} · DATA BEFORE {until}</span></div>',unsafe_allow_html=True);st.markdown(branding.desk(team,until),unsafe_allow_html=True)
saved_since=st.session_state.filters.get('since') or window(until)
if saved_since>=until:saved_since=window(until)
context={**st.session_state.filters,'since':saved_since,**st.session_state.scenarios.get(team,{})}
def heading(title,desc):st.markdown('<h1>'+html.escape(title).replace('\n','<br>')+'</h1><div class="deck">'+html.escape(desc)+'</div>',unsafe_allow_html=True)
def table(df):
 labels={'player_name':'Player','player':'Player','attack_type':'Style (reference)','utility':'Scenario score','legal_balls':'Bowling balls','pp_allocated_balls':'PP balls','mid_allocated_balls':'Middle balls','death_allocated_balls':'Death balls','strike_rate':'Strike rate','score':'Descriptive score','reliability':'Sample weight','player_id':'Registry ID','cricsheet_id':'Registry ID','evidence_missing':'No observed evidence','bowling_capacity':'Max overs','pp_capacity':'PP max overs','mid_capacity':'Middle max overs','death_capacity':'Death max overs'}
 st.dataframe(df.head(500).style.format(precision=2).set_properties(**{'background-color':palette['panel'],'color':palette['text']}),hide_index=True,width='stretch',column_config={k:v for k,v in labels.items() if k in df})
 if len(df)>500:st.caption('Showing 500 rows. Export retains the full selection.')
def download(df,name):st.download_button('Export CSV',df.to_csv(index=False),name,'text/csv')
def chart(df,x,y):
 c=alt.Chart(df).mark_bar(color=palette['accent'],cornerRadiusTopLeft=3,cornerRadiusTopRight=3).encode(x=alt.X(x,sort=None),y=alt.Y(y),tooltip=list(df.columns)).properties(height=230).configure(background=palette['bg']).configure_axis(labelColor=palette['text'],titleColor=palette['text'],gridColor=palette['border']).configure_view(stroke=None);st.altair_chart(c,width='stretch')
def planning_kwargs():return {k:context[k] for k in ['excluded','locked','costs','budget','min_bowlers','min_batters','min_spin','min_pace','overrides'] if k in context}
if page=='Decision desk':
 heading('Decisions with\nan evidence trail.','Your filters, roster date, exclusions and budget travel with the brief. Numerical facts are rendered from successful tools; the model selects evidence and next actions.')
 left,right=st.columns([1.8,1],gap='large')
 with left:
  intent=st.selectbox('Research task',['Scouting','XI planning','Player evidence','Match research']);mode=st.radio('Briefing mode',['Local evidence','DeepSeek analyst'],horizontal=True)
  player_query=st.text_input('Player name or alias') if intent=='Player evidence' else ''
  q=st.text_area('Decision question',value=f'Compare {context["phase"].lower()} options for {team} using the active evidence and scenario.',max_chars=2000,height=100)
  if st.button('Prepare brief',type='primary'):
   # Clear previous output BEFORE the request; failures cannot display an old answer.
   st.session_state.pop('brief',None);st.session_state.pop('brief_error',None)
   try:
    if mode=='DeepSeek analyst':
     with st.spinner('Retrieving, checking and selecting evidence…'):b=ask(q+(' Player: '+player_query if player_query else ''),p,s,model,team,until,key(),owner,{**context,'intent':intent},quota_owner=quota_owner)
    else:
     tool={'Scouting':'scout_players','XI planning':'optimize_xi','Player evidence':'player_dossier','Match research':'match_prediction'}[intent];args={'name':player_query} if intent=='Player evidence' else ({'team1':team,'team2':'MI' if team!='MI' else 'CSK'} if intent=='Match research' else {})
     result=safe(dispatch(tool,args,p,s,model,team,until,context));facts={};fact_rows(result,facts);ids=list(facts)[:32];b={'text':render(ids,facts,['availability','compare'] if ids else ['sample']),'question':q,'team':team,'until':until,'scenario':context,'facts':facts,'trace':[{'tool':tool,'result':result}],'mode':'Local evidence · no API call','status':'grounded' if ids else 'insufficient'}
    st.session_state.brief=b
   except (ValueError,RuntimeError) as ex:st.session_state.brief_error=str(ex)
  if st.session_state.get('brief_error'):st.error(st.session_state.brief_error)
  if 'brief' in st.session_state:
   b=st.session_state.brief
   if b['team']!=team or b['until']!=until:st.info('A previous brief uses a different desk or date. Prepare a new one to apply this context.')
   st.caption(f"{b['mode']} · {b['team']} · before {b['until']}");st.markdown('**Question:** '+b['question']);st.markdown(b['text'])
   c=st.columns(2);c[0].download_button('Download brief',b['text'],'boundary-brief.md')
   if c[1].button('Save private brief'):
    if b['team']!=team:st.error('Switch to the brief’s desk before saving.')
    else:storage.save(owner,'briefs',b['question'][:100],safe(b));st.success('Saved to this private session and team.')
   with st.expander('Evidence, filters and tool trace'):st.json(safe({k:b.get(k) for k in ['facts','trace','usage','scenario']}))
 with right:
  st.subheader('Active research context');st.write(f"**{team}** · {context['competition']} · {context['discipline']} · {context['phase']}");st.caption('Set evidence filters in Scouting; set availability, costs and capability assumptions in Squad scenarios.')
  if context.get('excluded'):st.write('Excluded: '+', '.join(context['excluded']))
  st.subheader('Evidence coverage')
  for source in audit['sources']:st.caption(f"{source['competition']} / {source['included']:,} matches / through {source['latest']}")
  st.info('No verified current injury feed. Historical auction prices are not current valuations.')
elif page=='Scouting & comparison':
 heading('Find the role.\nInspect the evidence.','Scores include scoring rate, dismissals or wicket taking, with one-year recency decay and a 120-ball shrinkage prior. Weights remain transparent research assumptions.')
 c=st.columns(4);competition=c[0].selectbox('Competition',['IPL','BBL','SMAT','Hundred','T20I','ALL'],index=['IPL','BBL','SMAT','Hundred','T20I','ALL'].index(context['competition']),key='filter_comp');discipline=c[1].selectbox('Discipline',['Bowling','Batting'],index=['Bowling','Batting'].index(context['discipline']),key='filter_discipline');phase=c[2].selectbox('Phase',['Death','Powerplay','Middle','All'],index=['Death','Powerplay','Middle','All'].index(context['phase']),key='filter_phase');minimum=c[3].number_input('Minimum phase balls',1,2000,int(context['min_balls']),30,key='filter_min')
 since=st.date_input('Evidence window starts',value=pd.Timestamp(context['since']).date(),max_value=cutoff-datetime.timedelta(days=1)).isoformat();st.session_state.filters={'competition':competition,'discipline':discipline,'phase':phase,'min_balls':int(minimum),'since':since}
 r=scout(p,competition,since,int(minimum),discipline,until,phase);search=st.text_input('Find a player or alias')
 if search:
  ids={x['player_id'] for x in resolve(p,search)};r=r[r.player_id.isin(ids)]
 cols=['player']+(['competition'] if competition=='ALL' else [])+['score','reliability','runs','balls','dismissals','wickets','legal_balls','strike_rate','economy'];table(r[cols]);download(r,'scouting.csv')
 st.caption('ALL shows separate competition groups; scores are not IPL-equivalent projections. Raw totals remain unweighted. Sample weight uses recency-adjusted workload, not probability of success.')
 chosen=st.multiselect('Compare up to three player IDs',r.player_id.drop_duplicates().tolist(),default=r.player_id.drop_duplicates().head(2).tolist(),max_selections=3,format_func=lambda x:r[r.player_id==x].player.iloc[0])
 selected=r[r.player_id.isin(chosen)]
 if len(selected):
  table(selected[cols]);chart(selected.assign(label=selected.player+(' / '+selected.competition if competition=='ALL' else '')),'label:N','score:Q')
  for row in selected.itertuples():st.caption(row.player+' · '+json.dumps(player_interval(p,row.player_id,discipline,until,since,getattr(row,'competition',competition),phase)))
elif page=='Squad & auction scenarios':
 heading('Build the XI.\nAccount for every over.','Selection is constrained by observed workload, phase experience and dated squad membership. No unobserved player receives an automatic performance value.')
 try:r=roster_scores(p,s,team,until)
 except ValueError as ex:st.warning(str(ex));st.stop()
 old=st.session_state.scenarios.get(team,{})
 c=st.columns(2);excluded=c[0].multiselect('Unavailable / exclude',r.player_name.tolist(),default=[n for n in old.get('excluded',[]) if n in set(r.player_name)],key='exclude_'+team);locked=c[1].multiselect('Must include',r.player_name.tolist(),default=[n for n in old.get('locked',[]) if n in set(r.player_name)],key='lock_'+team)
 c=st.columns(4);min_spin=c[0].slider('Minimum spin options',0,3,old.get('min_spin',1),key='spin_'+team);min_pace=c[1].slider('Minimum pace options',0,5,old.get('min_pace',2),key='pace_'+team);budget_on=c[2].checkbox('Apply XI budget',value=old.get('budget') is not None,key='budget_on_'+team);edit=c[3].checkbox('Capability assumptions',value=bool(old.get('overrides')),key='override_on_'+team)
 overrides=old.get('overrides',{}) if edit else {}
 if edit:
  st.caption('Reference attack types are curated planning tags. Confirm them. A manual workload/utility override needs a written reason and remains a scenario assumption.')
  name=st.selectbox('Override player',r.player_name.tolist());cap=st.number_input('Maximum overs assumption',0.,4.,4.,.5);attack=st.selectbox('Attack type assumption',['Pace','Spin','Unknown']);reason=st.text_input('Justification / source');utility=st.number_input('Utility assumption for an unobserved player',value=0.)
  if reason.strip():overrides={name:{'capacity':cap,'pp':cap,'mid':cap,'death':cap,'attack_type':attack,'reason':reason,'utility':utility}}
 costs=None;budget=None
 if budget_on:
  budget=st.number_input('XI scenario budget (₹ Cr)',0.,500.,float(old.get('budget') or 30.),1.,key='budget_'+team);st.caption('Prices are analyst assumptions, not estimated market values. Defaults are placeholders.')
  editor=st.data_editor(pd.DataFrame({'Player':r.player_name,'Cost (₹ Cr)':r.player_name.map(old.get('costs') or {}).fillna(1.)}),hide_index=True,disabled=['Player'],column_config={'Cost (₹ Cr)':st.column_config.NumberColumn(min_value=0.,max_value=100.)},key='cost_'+team);costs=dict(zip(editor.Player,editor['Cost (₹ Cr)']))
 scenario={'excluded':excluded,'locked':locked,'min_spin':min_spin,'min_pace':min_pace,'min_bowlers':5,'min_batters':5,'costs':costs,'budget':budget,'overrides':overrides};st.session_state.scenarios[team]=scenario
 result=optimize(r,**scenario)
 if result['ok']:
  c=st.columns(4);c[0].metric('Selected',11);c[1].metric('Overseas',str(result['overseas'])+' / 4');c[2].metric('Workload-supported options',result['bowlers']);c[3].metric('Allocated balls',120)
  cols=['player_name','attack_type','utility','legal_balls','pp_allocated_balls','mid_allocated_balls','death_allocated_balls'];table(result['players'][cols]);download(result['players'][cols],'XI-and-bowling-plan.csv')
  st.caption('Powerplay / middle / death allocation: 36 / 60 / 24 legal balls. Maximum 24 balls per player. This is a full twenty-over planning model; no Impact Player certification or pitch suitability is implied.')
  if st.button('Save private scenario'):storage.save(owner,'briefs',team+' XI and workload scenario',safe({'team':team,'until':until,'scenario':scenario,'players':result['players'][cols].to_dict('records')}));st.success('Saved privately.')
 else:st.warning(result['reason'])
 with st.expander('Evidence coverage and assumptions'):
  table(r[['player_name','attack_type','role','balls','legal_balls','bowling_capacity','pp_capacity','mid_capacity','death_capacity','evidence_missing']]);st.write('Default bowling evidence: 120 total balls, plus 36 PP / 36 middle / 24 death balls for phase eligibility. These are explicit planning thresholds, not official eligibility rules. Each selected player is capped at four overs. Missing evidence blocks selection unless you supply a justified assumption. Known trade events are sourced; the rest of the supplied roster has not been fully reverified.')
elif page=='Player dossier':
 heading('Resolve the player.\nRead the relevant sample.','Official display corrections preserve archive aliases and registry IDs. Uncertainty uses the same competition, phase and dates as the selected evidence.')
 query=st.text_input('Player name or scorecard alias',value=st.session_state.get('dossier_query','Virat Kohli'),key='dossier_search');hits=resolve(p,query)
 if not hits:st.info('No match. Check an alias or registry ID. No statistics have been inferred.');st.stop()
 hit=st.selectbox('Confirm identity',hits,format_func=lambda x:x['player']+' · '+x['player_id']);st.session_state.dossier_query=hit['player'];z=select_window(p,context['competition'],context['since'],until,context['phase']);z=z[z.player_id==hit['player_id']]
 st.caption(f"Active scope: {context['competition']} / {context['phase']} / {context['since']} to before {until}.")
 c=st.columns(3);c[0].metric('Runs',int(z.runs.sum()));c[1].metric('Wickets',int(z.wickets.sum()));c[2].metric('Named appearances',len(z))
 season=z.groupby(['competition','season'],as_index=False)[['runs','balls','wickets','legal_balls']].sum();table(season)
 if len(season):chart(season.assign(label=season.season+' / '+season.competition),'label:N','runs:Q')
 st.caption('Uncertainty for active filters: '+json.dumps(player_interval(p,hit['player_id'],context['discipline'],until,context['since'],context['competition'],context['phase'])))
 with st.expander('Match evidence'):table(z[['date','competition','team','runs','balls','wickets','legal_balls']].sort_values('date',ascending=False))
 st.subheader('Historical auction lookup');st.caption('2013–2022 source records; units and transaction types remain unverified. Search is manual to avoid false identity joins. Not a current valuation.');auction_q=st.text_input('Auction name',value=hit['player']);table(a[a.Player.str.contains(auction_q,case=False,regex=False)])
elif page=='Match research':
 heading('A benchmark must\nearn its place.','The research model did not beat a training-derived chase-rate baseline in validation and held-out testing. That baseline is the main scenario estimate; the model remains visible for scrutiny.')
 teams=list(branding.TEAMS);c=st.columns(2);t1=c[0].selectbox('Team A',teams,index=teams.index(team),key='t1_'+team);t2=c[1].selectbox('Team B',[t for t in teams if t!=t1],key='t2_'+team);chase=st.selectbox('Chasing team',['Unknown',t1,t2]);venue=st.selectbox('Canonical venue',sorted(model['state']['venues']))
 if until<=model['state']['last_date']:st.info('The snapshot is after this cutoff. Current scenario estimates are disabled; use the dated holdout records below.')
 else:
  pr=predict(model,t1,t2,venue,None if chase=='Unknown' else chase);c=st.columns(2);c[0].metric('Pre-toss baseline', '50% · no validated edge');c[1].metric(t1+' post-toss baseline',f"{pr['post']:.1%}" if pr['post'] is not None else 'Select chasing team');st.caption(pr['method']+'. Squad edits are not prediction inputs; this is not an injury or weather simulator.')
 st.subheader('Held-out forecasts and stronger baselines');table(pd.DataFrame(report['test']).T.reset_index(names='Method'));st.json(report['gate'])
 with st.expander('Season results, calibration and assumptions'):st.json(report)
 download(pd.read_csv(ROOT/'data/prediction_holdout.csv'),'historical-forecasts.csv')
elif page=='Decision journal':
 heading('Private research.\nA record of the reasoning.','Only this browser session and selected franchise can read these records. Legacy shared records are never loaded. Account-based durable team access is outside this public demo.')
 rows=storage.records(owner)
 for row in rows:
  with st.expander(row['title']+' · '+row['created'][:10]):
   if row['payload'].get('text'):st.markdown(row['payload']['text'])
   st.json(row['payload'])
 if not rows:st.info('Save a brief or scenario from this desk to begin.')
 else:st.download_button('Export private journal',json.dumps(rows,indent=2),'private-journal.json')
elif page=='Evaluation & sources':
 heading('Claims that can\nbe checked.','Read the actual regression results, source dates, accepted baseline and known boundaries. Submitted feedback is not presented as independently verified expert validation.')
 tabs=st.tabs(['Checks','Review','Sources & squads','SWOT'])
 with tabs[0]:
  f=ROOT/'data/release_checks.json'
  st.json(json.loads(f.read_text()) if f.exists() else {'status':'Checks pending; no pass status inferred.'});st.write('Provider connectivity depends on this deployment. Live model quality is not established by offline mocks. Settings shows a scoped connection test when you supply a session key.');st.json(report['gate'])
 with tabs[1]:
  with st.form('review'):
   reviewer=st.text_input('Reviewer alias');task=st.text_area('Task and brief evaluated');ratings={x:st.select_slider(x,['Not assessed',1,2,3,4,5],value='Not assessed') for x in ['Evidence support','Role relevance','Clarity','Usefulness']};notes=st.text_area('Observed failure or supporting evidence');submit=st.form_submit_button('Save private review')
   if submit:
    if not reviewer.strip() or not task.strip():st.error('Identify the reviewer and evaluated task.')
    else:storage.save(owner,'reviews',reviewer,{'task':task,'ratings':ratings,'notes':notes});st.success('Saved privately; not an authenticated expert rating.')
  reviews=storage.records(owner,'reviews')
  if reviews:st.download_button('Export private reviews',json.dumps(reviews,indent=2),'reviews.json')
 with tabs[2]:
  table(pd.DataFrame(audit['sources']));st.json(json.loads((ROOT/'data/squad_events.json').read_text()))
  for note in audit['notes']:st.caption(note)
 with tabs[3]:
  table(pd.DataFrame({'Strength':['Traceable match records','Exact workload solver','Scoped evidence rendering'],'Weakness':['Heuristic scoring weights','Partial squad verification','No demonstrated forecast edge'],'Opportunity':['Expert role evaluation','Dated squad registry','Historical scouting validation'],'Threat':['Stale eligibility','Source rights and drift','Public API allowance abuse']}))
else:
 heading('Clear boundaries.\nPrivate credentials.','The shared hosting key is never displayed or exported. Session overrides stay in server memory. This public demonstration does not provide authenticated accounts.')
 st.success('Hosting or session key configured.' if key() else 'No DeepSeek key configured. Local research remains available.')
 new=st.text_input('Use your own key for this session',type='password')
 if st.button('Set session key'):
  if new.startswith('sk-') and len(new)>12:st.session_state.private_key=new;st.success('Session override saved in memory; authentication is checked only by the provider.')
  else:st.error('Enter a provider key.')
 if st.button('Test my session key',disabled=not bool(st.session_state.get('private_key'))):
  try:provider([{'role':'user','content':'Return {"selected_fact_ids":[],"next_actions":[]}'}],st.session_state.private_key,quota_owner);st.success('Provider responded. This does not validate analytical quality.')
  except RuntimeError as ex:st.error(str(ex))
 st.json(storage.usage(quota_owner));st.caption('Six provider calls per private session across teams per UTC day; thirty per installation. Resetting a session is not an abuse-resistant identity boundary. Restrict public access or add authenticated hosting for sensitive use. Local storage can be ephemeral: export work before closing or redeploying.')
 st.markdown('IPL and franchise marks identify the subjects of this independent educational project; no league or franchise endorsement is implied.')
