import streamlit as st
import pandas as pd
import anthropic
from datetime import date, datetime, timedelta
import json

st.set_page_config(
    page_title="CTI Assessment Scheduler",
    page_icon="🟣",
    layout="wide"
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.metric-card {
    background: #fff; border-radius: 10px; padding: 16px 20px;
    border: 1.5px solid #eaeff7; margin-bottom: 8px;
}
div[data-testid="stButton"] button[kind="primary"] {
    background: #0072ce; border: none;
}
</style>
""", unsafe_allow_html=True)

# ── SESSION STATE ─────────────────────────────────────────────────────────────
if 'joiners' not in st.session_state:
    st.session_state.joiners = []
if 'sent_status' not in st.session_state:
    st.session_state.sent_status = {}  # { e_number: 'sent' | 'error' | 'pending' }
if 'blocks' not in st.session_state:
    st.session_state.blocks = []  # list of blocked date strings

# ── HEADER ────────────────────────────────────────────────────────────────────
col_logo, col_stats = st.columns([3, 1])
with col_logo:
    st.markdown("""
    <div style="background:#0d1e3c;padding:16px 24px;border-radius:10px;margin-bottom:16px">
      <div style="font-size:20px;font-weight:800;color:#fff;letter-spacing:-0.5px">
        CTI<span style="color:#60a5fa">.</span> 
        <span style="font-size:15px;font-weight:600;color:#e2e8f0">Assessment Scheduler</span>
        <span style="font-size:12px;font-weight:400;color:#94a3b8"> · Pre-Embarkation</span>
      </div>
      <div style="font-size:11px;color:#64748b;margin-top:3px">
        15-min individual slots · Individual Teams meetings · Auto-record · New Hire only
      </div>
    </div>
    """, unsafe_allow_html=True)

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Setup")

    # Step 1: Upload
    st.markdown("**1 · Joiner List**")
    uploaded = st.file_uploader("Upload Joiners Report (.xlsx)", type=["xlsx", "xls"], label_visibility="collapsed")
    if uploaded:
        try:
            df = pd.read_excel(uploaded, sheet_name=None)
            sheet = next((s for s in df if 'PLANNED' in s.upper()), list(df.keys())[0])
            df = df[sheet]
            df.columns = df.columns.str.strip()
            new_hires = df[df['Employment Status'].str.strip() == 'New Hire'].copy()
            
            joiners = []
            for _, row in new_hires.iterrows():
                embark = row.get('Embark Date', '')
                if pd.notna(embark):
                    try:
                        embark_str = pd.to_datetime(embark).strftime('%Y-%m-%d')
                    except:
                        embark_str = str(embark)[:10]
                else:
                    embark_str = ''
                
                name = f"{row.get('Name','') or ''} {row.get('Surname','') or ''}".strip()
                if not name or not embark_str:
                    continue
                    
                joiners.append({
                    'e_number': str(row.get('E-Number Code', '') or '').strip(),
                    'name': name,
                    'email': str(row.get('Email', '') or '').strip(),
                    'position': str(row.get('Role Position', '') or '').strip(),
                    'department': str(row.get('Department', '') or '').strip(),
                    'ship': str(row.get('Ship', '') or '').strip(),
                    'embark_date': embark_str,
                    'embark_port': str(row.get('Embark Port', '') or '').strip(),
                    'cti_office': str(row.get('CTI Office', '') or '').strip(),
                })
            
            st.session_state.joiners = joiners
            st.session_state.sent_status = {}
            st.success(f"✅ {len(joiners)} New Hires loaded")
        except Exception as e:
            st.error(f"Error reading file: {e}")

    st.divider()

    # Step 2: Organizer
    st.markdown("**2 · Your Details**")
    org_name = st.text_input("Your Name", placeholder="Your Full Name")
    org_email = st.text_input("Your Email", placeholder="yourname@cti-indonesia.com")

    st.divider()

    # Step 3: Meeting Setup
    st.markdown("**3 · Meeting Setup**")
    subject = st.text_input("Subject", value="Pre-Embarkation Language Assessment — CTI Indonesia")
    
    col_s, col_e = st.columns(2)
    with col_s:
        daily_start = st.time_input("Daily Start", value=datetime.strptime("09:00", "%H:%M").time())
    with col_e:
        daily_end = st.time_input("Daily End", value=datetime.strptime("17:00", "%H:%M").time())
    
    window_days = st.selectbox("Assessment Window", [7, 14, 21, 30], index=3, 
                                format_func=lambda x: f"Within {x} days before embark")
    
    teams_link = st.text_input("Teams Meeting Link (optional)", 
                                placeholder="https://teams.microsoft.com/l/meetup-join/…",
                                help="Paste your Teams link — embedded into every invite with auto-record")
    
    body_text = st.text_area("Meeting Body", 
        value="You are invited to attend your Pre-Embarkation Language Assessment with CTI Indonesia. This is a required step to confirm your readiness before joining the ship. Please attend punctually and bring any relevant documents. We look forward to seeing you.",
        height=100)

    st.divider()

    # Step 4: CC
    st.markdown("**4 · CC Attendees**")
    cc_input = st.text_input("CC Emails", placeholder="email1@cti.com, email2@cti.com",
                              help="Comma-separated emails added to every invite")
    cc_emails = [e.strip() for e in cc_input.split(',') if e.strip() and '@' in e]

    st.divider()

    # Step 5: Block dates
    st.markdown("**5 · Block Dates**")
    block_date = st.date_input("Block a day", value=None, label_visibility="collapsed")
    block_reason = st.text_input("Reason (optional)", placeholder="e.g. Public holiday", key="block_reason")
    if st.button("🚫 Add Block", use_container_width=True):
        if block_date:
            ds = block_date.strftime('%Y-%m-%d')
            if ds not in [b['date'] for b in st.session_state.blocks]:
                st.session_state.blocks.append({'date': ds, 'label': block_reason or 'Blocked'})
                st.rerun()

    if st.session_state.blocks:
        for i, b in enumerate(st.session_state.blocks):
            col_b, col_x = st.columns([4, 1])
            with col_b:
                st.markdown(f"<div style='font-size:11px;color:#ef4444'>🚫 {b['date']} · {b['label']}</div>", 
                           unsafe_allow_html=True)
            with col_x:
                if st.button("✕", key=f"rmblock_{i}"):
                    st.session_state.blocks.pop(i)
                    st.rerun()

# ── SCHEDULE BUILDER ──────────────────────────────────────────────────────────
def build_schedule(joiners, daily_start, daily_end, window_days, blocks):
    """Auto-assign each joiner to a 15-min slot within their embark window."""
    blocked_days = {b['date'] for b in blocks}
    used_slots = {}  # { date_str: set of times }
    schedule = {}    # { date_str: [ {time, joiner} ] }

    sorted_joiners = sorted(
        [j for j in joiners if j['email'] and j['embark_date']], 
        key=lambda x: x['embark_date']
    )

    def get_slots(ds):
        start_mins = daily_start.hour * 60 + daily_start.minute
        end_mins = daily_end.hour * 60 + daily_end.minute
        total = (end_mins - start_mins) // 15
        return [f"{(start_mins + i*15)//60:02d}:{(start_mins + i*15)%60:02d}" for i in range(total)]

    for joiner in sorted_joiners:
        try:
            embark = datetime.strptime(joiner['embark_date'], '%Y-%m-%d').date()
        except:
            continue
        
        win_start = embark - timedelta(days=window_days)
        win_end = embark - timedelta(days=1)
        
        cursor = win_start
        assigned = False
        while cursor <= win_end and not assigned:
            ds = cursor.strftime('%Y-%m-%d')
            if ds not in blocked_days:
                if ds not in used_slots:
                    used_slots[ds] = set()
                for t in get_slots(ds):
                    if t not in used_slots[ds]:
                        used_slots[ds].add(t)
                        if ds not in schedule:
                            schedule[ds] = []
                        schedule[ds].append({'time': t, 'joiner': joiner})
                        assigned = True
                        break
            cursor += timedelta(days=1)

    # Sort each day's slots by time
    for ds in schedule:
        schedule[ds].sort(key=lambda x: x['time'])

    return schedule

# ── ICS BUILDER ───────────────────────────────────────────────────────────────
def esc(s):
    return (s or '').replace('\\','\\\\').replace(';','\\;').replace(',','\\,').replace('\n','\\n')

def build_ics_event(date_str, slot, subject, body_text, org_name, org_email, cc_emails, teams_link):
    joiner = slot['joiner']
    t = slot['time']
    h, m = map(int, t.split(':'))
    end_mins = h * 60 + m + 15
    end_time = f"{end_mins//60:02d}:{end_mins%60:02d}"
    
    start_ts = date_str.replace('-','') + 'T' + t.replace(':','') + '00'
    end_ts   = date_str.replace('-','') + 'T' + end_time.replace(':','') + '00'
    uid = f"CTI-ASSESS-{joiner['e_number']}-{date_str.replace('-','')}@cti-indonesia.com"
    now_ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    
    teams_section = ''
    if teams_link:
        teams_section = f"\n\n________________\nJoin Microsoft Teams Meeting\n{teams_link}\n\nNote: This meeting will be recorded.\n________________"
    
    full_body = (f"{body_text}{teams_section}\n\n"
                 f"Assessment Details:\nCandidate: {joiner['name']}\n"
                 f"Position: {joiner['position']}\nShip: {joiner['ship']}\n"
                 f"Embarkation: {joiner['embark_date']} from {joiner['embark_port']}\n"
                 f"E-Number: {joiner['e_number']}")
    
    attendees = f"ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;RSVP=TRUE;CN={esc(joiner['name'])}:mailto:{joiner['email']}"
    for cc in cc_emails:
        attendees += f"\r\nATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;RSVP=FALSE:mailto:{cc}"
    
    organizer = (f"ORGANIZER;CN={esc(org_name or org_email)}:mailto:{org_email}" 
                 if org_email else "ORGANIZER:mailto:noreply@cti-indonesia.com")
    
    location = "Microsoft Teams Meeting" if teams_link else "Online"
    
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now_ts}",
        f"DTSTART:{start_ts}",
        f"DTEND:{end_ts}",
        f"SUMMARY:{esc(subject)} — {esc(joiner['name'])}",
        f"DESCRIPTION:{esc(full_body)}",
        f"LOCATION:{location}",
        organizer,
        attendees,
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
    ]
    if teams_link:
        lines += [
            f"X-MICROSOFT-SKYPETEAMSMEETINGURL:{teams_link}",
            f"X-MICROSOFT-ONLINEMEETINGCONFLINK:{teams_link}",
            "X-MS-OLK-AUTORECORD:TRUE",
        ]
    lines.append("END:VEVENT")
    return "\r\n".join(lines)

def build_ics_file(events, org_name):
    cal_name = f"{org_name or 'CTI Indonesia'} — Pre-Embarkation Assessments"
    header = "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CTI Indonesia//Pre-Embarkation Scheduler//EN",
        f"X-WR-CALNAME:{esc(cal_name)}",
        "X-WR-TIMEZONE:Asia/Makassar",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
    ])
    return header + "\r\n" + "\r\n".join(events) + "\r\nEND:VCALENDAR"

# ── M365 TEAMS MEETING VIA ANTHROPIC MCP ─────────────────────────────────────
def create_teams_meeting(slot, date_str, subject, body_text, org_name, org_email, cc_emails):
    """Create a real Teams meeting via Microsoft 365 MCP connector."""
    joiner = slot['joiner']
    t = slot['time']
    h, m = map(int, t.split(':'))
    start_dt = f"{date_str}T{t}:00"
    end_mins = h * 60 + m + 15
    end_time = f"{end_mins//60:02d}:{end_mins%60:02d}"
    end_dt = f"{date_str}T{end_time}:00"
    
    cc_line = f"CC attendees: {', '.join(cc_emails)}" if cc_emails else ''
    org_line = f"Organizer: {org_name} <{org_email}>" if org_name and org_email else ''
    
    prompt = f"""Create a Microsoft 365 Teams calendar event with these exact details:
Subject: "{subject} — {joiner['name']}"
Start: {start_dt}
End: {end_dt}
Required attendee: {joiner['email']}
{cc_line}
{org_line}
Body: {body_text}

Candidate: {joiner['name']}, {joiner['position']}, Ship: {joiner['ship']}, Embark: {joiner['embark_date']} from {joiner['embark_port']}, E-Number: {joiner['e_number']}.

Create as an online Teams meeting with a unique link. Enable auto-recording. Send invite to all attendees.
Reply ONLY: DONE if successful, or ERROR: <reason> if not."""

    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    response = client.beta.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
        mcp_servers=[{
            "type": "url",
            "url": "https://microsoft365.mcp.claude.com/mcp",
            "name": "microsoft365",
        }],
        betas=["mcp-client-2025-04-04"],
    )
    
    text = ''.join(b.text for b in response.content if hasattr(b, 'text'))
    if text.strip().upper().startswith('ERROR'):
        raise Exception(text.replace('ERROR:', '').strip())
    return True

# ── MAIN CONTENT ──────────────────────────────────────────────────────────────
joiners = st.session_state.joiners

if not joiners:
    st.info("👈 Upload a Joiners Report Excel file in the sidebar to get started.")
    st.stop()

# Build schedule
schedule = build_schedule(joiners, daily_start, daily_end, window_days, st.session_state.blocks)
total_scheduled = sum(len(v) for v in schedule.values())
total_sent = sum(1 for s in st.session_state.sent_status.values() if s == 'sent')
unscheduled = [j for j in joiners if not any(
    any(s['joiner']['e_number'] == j['e_number'] for s in slots) 
    for slots in schedule.values()
)]

# Stats row
c1, c2, c3, c4 = st.columns(4)
c1.metric("New Hires", len(joiners))
c2.metric("Scheduled", total_scheduled)
c3.metric("Invited ✓", total_sent)
c4.metric("Outside Window", len(unscheduled))

st.divider()

# ── FILTERS ───────────────────────────────────────────────────────────────────
st.markdown("### 👥 Joiner List")

fcol1, fcol2, fcol3, fcol4, fcol5 = st.columns([3, 2, 2, 2, 2])
with fcol1:
    search_q = st.text_input("🔍 Search", placeholder="Name, position, ship…", label_visibility="collapsed")
with fcol2:
    ships = ['All Ships'] + sorted(set(j['ship'] for j in joiners if j['ship']))
    ship_filter = st.selectbox("Ship", ships, label_visibility="collapsed")
with fcol3:
    depts = ['All Depts'] + sorted(set(j['department'] for j in joiners if j['department']))
    dept_filter = st.selectbox("Dept", depts, label_visibility="collapsed")
with fcol4:
    embark_from = st.date_input("From", value=None, label_visibility="collapsed", key="efrom")
with fcol5:
    embark_to = st.date_input("To", value=None, label_visibility="collapsed", key="eto")

# Apply filters
filtered = joiners
if search_q:
    q = search_q.lower()
    filtered = [j for j in filtered if q in (j['name']+j['position']+j['ship']+j['e_number']).lower()]
if ship_filter != 'All Ships':
    filtered = [j for j in filtered if j['ship'] == ship_filter]
if dept_filter != 'All Depts':
    filtered = [j for j in filtered if j['department'] == dept_filter]
if embark_from:
    filtered = [j for j in filtered if j['embark_date'] >= embark_from.strftime('%Y-%m-%d')]
if embark_to:
    filtered = [j for j in filtered if j['embark_date'] <= embark_to.strftime('%Y-%m-%d')]

st.caption(f"Showing {len(filtered)} of {len(joiners)} new hires")

# ── JOINER ROWS ───────────────────────────────────────────────────────────────
# Find each joiner's scheduled date/time
def get_slot(e_number):
    for ds, slots in schedule.items():
        for sl in slots:
            if sl['joiner']['e_number'] == e_number:
                return ds, sl
    return None, None

for joiner in filtered:
    status = st.session_state.sent_status.get(joiner['e_number'], 'pending')
    sched_date, sched_slot = get_slot(joiner['e_number'])
    no_email = not joiner['email']

    col_info, col_ship, col_slot, col_btn = st.columns([4, 1.5, 2, 1.5])

    with col_info:
        name_style = "color:#16a34a;font-weight:700;" if status == 'sent' else "font-weight:700;"
        slot_info = f" · 📅 {sched_date} {sched_slot['time']}" if sched_date else " · <span style='color:#d97706'>Outside window</span>"
        no_email_tag = " · <span style='color:#dc2626;font-weight:600'>No email</span>" if no_email else ""
        st.markdown(
            f"<div style='{name_style}font-size:13px'>{joiner['name']}"
            f"{'  ✓' if status == 'sent' else ''}</div>"
            f"<div style='font-size:11px;color:#8a96b0'>{joiner['position']} · E-{joiner['e_number']} · Embark {joiner['embark_date']}{slot_info}{no_email_tag}</div>",
            unsafe_allow_html=True
        )

    with col_ship:
        st.markdown(
            f"<div style='background:#0d1e3c;color:#fff;font-size:10px;font-weight:700;"
            f"padding:3px 8px;border-radius:10px;display:inline-block;margin-top:8px'>{joiner['ship']}</div>",
            unsafe_allow_html=True
        )

    with col_slot:
        if sched_date:
            st.markdown(
                f"<div style='font-size:11px;color:#0072ce;font-weight:600;margin-top:10px'>📅 {sched_date}<br>{sched_slot['time']}</div>",
                unsafe_allow_html=True
            )

    with col_btn:
        if status == 'sent':
            st.markdown(
                "<div style='background:#dcfce7;color:#16a34a;font-size:11px;font-weight:700;"
                "padding:6px 10px;border-radius:8px;text-align:center;margin-top:6px'>✓ Invited</div>",
                unsafe_allow_html=True
            )
        elif no_email:
            st.markdown(
                "<div style='background:#fef3c7;color:#d97706;font-size:11px;font-weight:700;"
                "padding:6px 10px;border-radius:8px;text-align:center;margin-top:6px'>No email</div>",
                unsafe_allow_html=True
            )
        elif status == 'error':
            if st.button("⚠️ Retry", key=f"retry_{joiner['e_number']}"):
                if sched_slot and sched_date:
                    try:
                        with st.spinner(f"Sending to {joiner['name']}…"):
                            create_teams_meeting(sched_slot, sched_date, subject, body_text, org_name, org_email, cc_emails)
                        st.session_state.sent_status[joiner['e_number']] = 'sent'
                    except Exception as e:
                        st.error(str(e))
                    st.rerun()
        else:
            btn_label = "📅 Invite" if sched_date else "📋 Manual"
            if st.button(btn_label, key=f"invite_{joiner['e_number']}", 
                        disabled=(not sched_date and not joiner['email'])):
                if sched_slot and sched_date:
                    try:
                        with st.spinner(f"Creating Teams meeting for {joiner['name']}…"):
                            create_teams_meeting(sched_slot, sched_date, subject, body_text, org_name, org_email, cc_emails)
                        st.session_state.sent_status[joiner['e_number']] = 'sent'
                        st.success(f"✅ Teams invite sent to {joiner['name']} — {sched_date} at {sched_slot['time']}")
                    except Exception as e:
                        st.session_state.sent_status[joiner['e_number']] = 'error'
                        st.error(f"Failed: {e}")
                    st.rerun()

    st.divider()

# ── DOWNLOAD ICS FALLBACK ─────────────────────────────────────────────────────
st.markdown("### 📥 Download .ics (Fallback)")
st.caption("Use if Teams connector is unavailable — import into Outlook to send from your account.")

dl_col1, dl_col2 = st.columns(2)
with dl_col1:
    if st.button("📦 Download All as .ics", use_container_width=True):
        events = []
        for ds, slots in sorted(schedule.items()):
            for slot in slots:
                events.append(build_ics_event(ds, slot, subject, body_text, org_name, org_email, cc_emails, teams_link))
        ics_content = build_ics_file(events, org_name)
        st.download_button(
            "⬇️ Save All_Assessments.ics",
            data=ics_content.encode('utf-8'),
            file_name=f"CTI_All_Assessments.ics",
            mime="text/calendar",
            use_container_width=True
        )

with dl_col2:
    if filtered:
        if st.button("📄 Download Filtered as .ics", use_container_width=True):
            events = []
            filtered_enums = {j['e_number'] for j in filtered}
            for ds, slots in sorted(schedule.items()):
                for slot in slots:
                    if slot['joiner']['e_number'] in filtered_enums:
                        events.append(build_ics_event(ds, slot, subject, body_text, org_name, org_email, cc_emails, teams_link))
            if events:
                ics_content = build_ics_file(events, org_name)
                st.download_button(
                    "⬇️ Save Filtered.ics",
                    data=ics_content.encode('utf-8'),
                    file_name=f"CTI_Filtered_Assessments.ics",
                    mime="text/calendar",
                    use_container_width=True
                )
            else:
                st.warning("No scheduled meetings in current filter.")

st.divider()

# ── MANUAL INVITE ─────────────────────────────────────────────────────────────
st.markdown("### ✍️ Manual Invite")
st.caption("Send a Teams meeting to anyone — from the joiner list or enter details manually.")

tab_list, tab_custom = st.tabs(["Pick from Joiner List", "Enter Manually"])

with tab_list:
    if not joiners:
        st.info("Upload a Joiners Report first.")
    else:
        joiner_options = {f"{j['name']} · {j['position']} · {j['ship']} · Embark {j['embark_date']}": j 
                         for j in joiners if j['email']}
        if not joiner_options:
            st.warning("No joiners with email addresses found.")
        else:
            selected_label = st.selectbox("Select Joiner", list(joiner_options.keys()), 
                                           label_visibility="collapsed")
            selected_joiner = joiner_options[selected_label]
            
            mc1, mc2 = st.columns(2)
            with mc1:
                manual_date_list = st.date_input("Meeting Date", value=date.today(), key="manual_date_list")
            with mc2:
                manual_time_list = st.time_input("Meeting Time", 
                                                  value=datetime.strptime("09:00", "%H:%M").time(),
                                                  key="manual_time_list")
            
            if st.button("📅 Send Teams Invite", key="send_manual_list", use_container_width=True, type="primary"):
                slot = {'time': manual_time_list.strftime('%H:%M'), 'joiner': selected_joiner}
                ds = manual_date_list.strftime('%Y-%m-%d')
                try:
                    with st.spinner(f"Creating Teams meeting for {selected_joiner['name']}…"):
                        create_teams_meeting(slot, ds, subject, body_text, org_name, org_email, cc_emails)
                    st.session_state.sent_status[selected_joiner['e_number']] = 'sent'
                    st.success(f"✅ Teams invite sent to {selected_joiner['name']} — {ds} at {slot['time']}")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to send: {e}")
                    # Fallback: offer .ics download
                    event = build_ics_event(ds, slot, subject, body_text, org_name, org_email, cc_emails, teams_link)
                    ics = build_ics_file([event], org_name)
                    safe_name = selected_joiner['name'].replace(' ', '_')
                    st.download_button(
                        "📥 Download .ics instead",
                        data=ics.encode('utf-8'),
                        file_name=f"Assessment_{safe_name}_{ds}.ics",
                        mime="text/calendar"
                    )

with tab_custom:
    st.caption("For candidates not in the current joiner file.")
    cc1, cc2 = st.columns(2)
    with cc1:
        manual_name = st.text_input("Full Name", placeholder="e.g. John Smith")
        manual_position = st.text_input("Position (optional)", placeholder="e.g. Dining Steward")
        manual_date_custom = st.date_input("Meeting Date", value=date.today(), key="manual_date_custom")
    with cc2:
        manual_email = st.text_input("Email Address", placeholder="john@gmail.com")
        manual_ship = st.text_input("Ship (optional)", placeholder="e.g. Queen Anne")
        manual_time_custom = st.time_input("Meeting Time",
                                            value=datetime.strptime("09:00", "%H:%M").time(),
                                            key="manual_time_custom")

    if st.button("📅 Send Teams Invite", key="send_manual_custom", use_container_width=True, type="primary"):
        if not manual_name or not manual_email:
            st.warning("Please enter a name and email.")
        elif '@' not in manual_email:
            st.warning("Please enter a valid email address.")
        else:
            custom_joiner = {
                'e_number': f"MANUAL-{int(datetime.now().timestamp())}",
                'name': manual_name,
                'email': manual_email,
                'position': manual_position or '',
                'ship': manual_ship or '',
                'embark_date': '',
                'embark_port': '',
                'department': '',
                'cti_office': ''
            }
            slot = {'time': manual_time_custom.strftime('%H:%M'), 'joiner': custom_joiner}
            ds = manual_date_custom.strftime('%Y-%m-%d')
            try:
                with st.spinner(f"Creating Teams meeting for {manual_name}…"):
                    create_teams_meeting(slot, ds, subject, body_text, org_name, org_email, cc_emails)
                st.success(f"✅ Teams invite sent to {manual_name} — {ds} at {slot['time']}")
            except Exception as e:
                st.error(f"Failed to send: {e}")
                event = build_ics_event(ds, slot, subject, body_text, org_name, org_email, cc_emails, teams_link)
                ics = build_ics_file([event], org_name)
                safe_name = manual_name.replace(' ', '_')
                st.download_button(
                    "📥 Download .ics instead",
                    data=ics.encode('utf-8'),
                    file_name=f"Assessment_{safe_name}_{ds}.ics",
                    mime="text/calendar"
                )
