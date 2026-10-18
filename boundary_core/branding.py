from pathlib import Path
import base64, html

ROOT = Path(__file__).resolve().parents[1]
TEAMS = {
    "CSK": ("Chennai Super Kings", "#936100", "#F6CB47"),
    "DC": ("Delhi Capitals", "#1756AD", "#72AAFF"),
    "GT": ("Gujarat Titans", "#705B2A", "#D7BC75"),
    "KKR": ("Kolkata Knight Riders", "#7043A0", "#C0A0F0"),
    "LSG": ("Lucknow Super Giants", "#006B87", "#65D2E6"),
    "MI": ("Mumbai Indians", "#0065AA", "#75BBFF"),
    "PBKS": ("Punjab Kings", "#B02736", "#FF8995"),
    "RCB": ("Royal Challengers Bengaluru", "#AB2436", "#FF8798"),
    "RR": ("Rajasthan Royals", "#A61C69", "#FF88C4"),
    "SRH": ("Sunrisers Hyderabad", "#A94C09", "#FFA25D"),
}


def logo(team):
    p = ROOT / "assets" / f"{team}.svg"
    return "data:image/svg+xml;base64," + base64.b64encode(p.read_bytes()).decode()


def css(team, theme):
    dark = theme == "Dark"
    accent = TEAMS[team][2 if dark else 1]
    bg = "#101820" if dark else "#F6F5F0"
    panel = "#19242E" if dark else "#FFFFFF"
    side = "#131E27" if dark else "#EDEFE8"
    text = "#E8EDF1" if dark else "#192D34"
    muted = "#A8B8C5" if dark else "#596B72"
    border = "#334553" if dark else "#D3DCD7"
    return f"""<style>
 :root{{--ink:{text};--muted:{muted};--paper:{bg};--panel:{panel};--line:{border};--accent:{accent}}}
 .stApp,[data-testid="stAppViewContainer"],header[data-testid="stHeader"]{{background:{bg};color:{text}}}
 .block-container{{padding:3rem 3rem 4rem;max-width:1480px}}[data-testid="stSidebar"]{{background:{side};border-right:1px solid {border}}}
 .stApp h1,.stApp h2,.stApp h3,.stApp label,.stApp p,.stApp li,.stApp summary{{color:{text}}}
 .stApp h1{{font-family:Georgia,serif!important;font-weight:400;letter-spacing:-1.5px;line-height:1.12;font-size:3.2rem!important}}.stApp h2,.stApp h3{{letter-spacing:-.5px}}
 .stApp [data-testid="stCaptionContainer"] p,.stApp [data-testid="stCaption"] p,.stApp [data-testid="stCaption"]{{color:{muted}!important;line-height:1.65}}
 .folio{{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;font-size:10px;letter-spacing:1.8px;border-bottom:1px solid {border};padding-bottom:15px;margin-bottom:24px;color:{muted}}}
 .desk{{display:flex;align-items:center;gap:18px;border-left:3px solid {accent};padding:18px 22px;background:linear-gradient(110deg,{panel},{bg});margin-bottom:26px;border-bottom:1px solid {border}}}
 .crest{{width:80px;height:80px;padding:9px;background:#fff;border-radius:12px;object-fit:contain}}.desk-name{{font-family:Georgia,serif;font-size:27px;color:{text}}}.desk-sub{{font-size:11px;letter-spacing:1.4px;color:{muted};margin-bottom:7px}} .deck{{max-width:790px;font-size:17px;color:{muted};line-height:1.7;margin-bottom:25px}}
 [data-testid="stMetric"]{{border-top:2px solid {accent};padding-top:12px}}[data-testid="stMetricValue"]{{font-family:Georgia,serif;color:{text}}}
 .stApp input,.stApp textarea,.stApp [data-baseweb="select"]>div,.stApp [data-baseweb="input"]>div{{background:{panel}!important;color:{text}!important;border-color:{border}!important}}
 .stApp [data-testid="stSelectbox"] [role="group"],.stApp [data-testid="stMultiSelect"] [role="group"],.stApp [data-testid="stMultiSelectTagsContainer"]{{background:{panel}!important;border-color:{border}!important;color:{text}!important}}
 .stApp [data-testid="stSelectbox"] button,.stApp [data-testid="stMultiSelect"] button,.stApp button[data-variant="segmented_control"]{{background:{panel}!important;color:{text}!important}}
 .stApp button[data-variant="segmented_control"] *{{color:{text}!important}}
 .stApp button[data-variant="segmented_control"][aria-checked="true"]{{box-shadow:inset 0 -2px {accent};border-color:{accent}!important}}
 .stApp [data-testid="stSidebarCollapseButton"] *,.stApp [data-testid="stSidebarCollapsedControl"] *{{color:{text}!important}}
 .stApp input::placeholder,.stApp textarea::placeholder{{color:{muted}!important;opacity:1}}
 .stApp [data-baseweb="select"] div{{color:{text}!important}}
 .stApp [data-baseweb="select"]>div>div{{background:{panel}!important}}
 .stApp [data-testid="stSegmentedControl"] button,.stApp [data-testid="stSegmentedControl"] [role="radio"]{{background:{panel}!important;color:{text}!important}}
 .stApp [data-testid="stSegmentedControl"] [aria-checked="true"]{{border-color:{accent}!important;box-shadow:inset 0 -2px {accent}}}
 .stApp [data-testid="stMarkdownContainer"].stCaption p{{color:{muted}!important}}
 .stApp [data-baseweb="select"] span,.stApp [data-baseweb="select"] svg{{color:{text}!important;fill:{text}}}
 div[role="listbox"],div[role="option"]{{background:{panel}!important;color:{text}!important}}.stApp button{{border-radius:5px;border-color:{border};background:{panel};color:{text}}}.stApp button p,.stApp button span{{color:inherit!important}}
 .stApp [data-testid="stBaseButton-primary"] *{{color:{'#101820' if dark else '#fff'}!important}}
 .stApp [data-testid="stBaseButton-primary"]{{background:{accent}!important;color:{'#101820' if dark else '#fff'}!important;border-color:{accent}!important}}
 .stApp [data-testid="stBaseButton-secondary"],.stApp [data-testid="stBaseButton-tertiary"]{{background:{panel};color:{text}}}
 .stApp details,.stApp [data-testid="stForm"]{{border-color:{border}!important}}.stApp [data-testid="stExpander"] details{{background:{panel}}}
 .stApp [data-testid="stSidebarCollapsedControl"] svg{{fill:{text}!important;color:{text}!important}}
 .stApp a{{color:{accent}}}.stApp hr{{border-color:{border}}}.stApp pre{{background:{panel};color:{text}}}
 .stApp [data-testid="stCaptionContainer"]{{opacity:1!important;color:{muted}!important}}
 .stApp [data-testid="stDateInputField"],.stApp [data-testid="stDateInput"] [role="group"]{{background:{panel}!important;color:{text}!important;border-color:{border}!important}}
 .stApp [data-testid="stDateInput"] [role="spinbutton"],.stApp [data-testid="stDateInput"] [data-type="literal"]{{color:{text}!important}}
 .stApp [data-testid="stDateInput"] button{{background:{panel}!important;color:{text}!important}}
 .home-brand{{display:flex;align-items:center;gap:16px;color:var(--muted);font-size:13px;margin:0 0 30px}}.home-brand .crest{{width:64px;height:64px}}
 .workflow{{display:grid;grid-template-columns:repeat(6,1fr);gap:0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin:36px 0 38px}}
 .workflow-step{{padding:22px 16px;border-right:1px solid var(--line)}}.workflow-step:last-child{{border:0}}.workflow-step span{{display:block;font-size:11px;color:var(--accent);margin-bottom:18px;letter-spacing:2px}}.workflow-step strong{{display:block;font-size:16px;color:var(--ink)}}.workflow-step p{{font-size:13px;line-height:1.6;margin:8px 0 0;color:var(--muted)}}
 .page-intro{{animation:arrive .32s ease-out}}.stApp button{{transition:background-color .15s ease,border-color .15s ease,box-shadow .15s ease}}.stApp button:hover{{border-color:var(--accent);box-shadow:0 2px 8px #00000012}}.stApp button:focus-visible{{outline:2px solid var(--accent);outline-offset:3px}}
 @keyframes arrive{{from{{opacity:.45;transform:translateY(6px)}}to{{opacity:1;transform:translateY(0)}}}}
 @media(prefers-reduced-motion:reduce){{*,*::before,*::after{{animation:none!important;transition:none!important;scroll-behavior:auto!important}}}}
 @media(max-width:1100px){{.workflow{{grid-template-columns:repeat(3,1fr)}}.workflow-step:nth-child(3){{border-right:0}}}}
 @media(max-width:700px){{.block-container{{padding:4.2rem 1rem 2rem}}.workflow{{grid-template-columns:repeat(2,1fr)}}.workflow-step{{padding:18px 12px}}.workflow-step:nth-child(3){{border-right:1px solid var(--line)}}.workflow-step:nth-child(even){{border-right:0}}.stApp h1{{font-size:2.4rem!important}}.desk{{padding:12px}}.desk-name{{font-size:22px}}.crest{{width:62px;height:62px}}}}
 </style>""", {
        "bg": bg,
        "panel": panel,
        "text": text,
        "accent": accent,
        "border": border,
    }


def desk(team, until):
    return f'<div class="desk"><img class="crest" src="{logo(team)}" alt="{team} logo"><div><div class="desk-sub">FRANCHISE RESEARCH / {team}</div><div class="desk-name">{TEAMS[team][0]}</div><div class="desk-sub" style="margin-top:8px">Evidence before {until} · dated roster events · human-reviewed decisions</div></div></div>'
