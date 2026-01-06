import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
import numpy as np
from pandas.tseries.offsets import BDay
import requests
from msal import ConfidentialClientApplication
from io import BytesIO
import matplotlib.pyplot as plt
import streamlit.components.v1 as components

st.set_page_config(
    layout="wide",  # makes content stretch full width
    page_title="Timesheet Dashboard"
    )

if not hasattr(st, "user") or not st.user.is_logged_in:
    st.title("Timesheet Dashboard")
    st.info("This app is private. Please log in with your Microsoft account.")
    if st.button("Log in with Microsoft"):
        st.login("microsoft")
    st.stop()

def get_sharepoint_file(client_id, client_secret, tenant_id, site_url, file_path):
    """
    Fetch CSV from SharePoint via Microsoft Graph
    """

    # Auth
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = ConfidentialClientApplication(
        client_id,
        client_credential=client_secret,
        authority=authority
    )

    token = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )

    if "access_token" not in token:
        raise Exception(f"Could not get token: {token}")

    headers = {"Authorization": f"Bearer {token['access_token']}"}

    # Resolve site ID
    hostname = site_url.split("//")[1].split("/")[0]
    site_path = "/" + "/".join(site_url.split("/")[3:])

    site_api = f"https://graph.microsoft.com/v1.0/sites/{hostname}:{site_path}"
    site_info = requests.get(site_api, headers=headers).json()

    if "id" not in site_info:
        raise Exception(f"Failed to resolve site: {site_info}")

    site_id = site_info["id"]

    # Fetch file from Documents drive (root)
    file_api = (
        f"https://graph.microsoft.com/v1.0/sites/{site_id}"
        f"/drive/root:/{file_path}:/content"
    )

    r = requests.get(file_api, headers=headers)
    r.raise_for_status()

    return pd.read_excel(BytesIO(r.content), engine ="openpyxl")

def donut_chart(used, remaining, title, footer):
    fig, ax = plt.subplots(figsize=(1, 1))

    ax.pie(
        [used, remaining],
        colors=["#ED017F", "#F7B3D6"],
        labels=None,
        startangle=90,
        counterclock=False,
        wedgeprops=dict(width=0.28),
    )

    ax.text(
        0, 0,
        f"{used:.1f}",
        ha="center",
        va="center",
        fontsize=10,
        fontweight="600",
        color="#111827"
    )
    ax.set_title(title, fontsize=7,fontweight="600",pad=6)
    ax.axis("equal")
    ax.axis("off")

    fig.text( 
        0.5,        # center horizontally
        0.02,       # near bottom of figure
        footer,
        ha="center",
        va="bottom",
        fontsize=5,
        color="#6b7280"
    )

    return fig

def target_hours_in_period(row, period_start, period_end):
    start = max(row["Start"], period_start)
    end = min(row["End"], period_end)

    if start > end:
        return 0

    weekdays = pd.bdate_range(start=start, end=end)
    return len(weekdays) * row["Daily_Hours"]

def adjusted_target_for_period(start_date, end_date):
    # Target hours in period (correct)
    target = (
        df_user[df_user["Full Name"] == emp_name]
        .apply(target_hours_in_period, axis=1, args=(start_date, end_date))
        .sum()
    )

    # PTO taken in period
    pto = df_util[
        (df_util["Date"].between(start_date, end_date)) &
        (df_util["Project No - Title"].isin([
            "PTO Vacation",
            "PTO Office Closed",
            "Stat Holidays",
            "Unpaid Time Off",
            "PTO Sick/Medical"
        ]))
    ]["Hours"].sum()

    return max(target - pto, 0)

emp_name = "Sumi Raveendiran"
first_name = emp_name.split(" ")[0]
today = datetime.today()
monday = today - timedelta(days=today.weekday())
last_refreshed = monday.strftime("%B %d, %Y")

col_left, col_right = st.columns([3, 1])

with col_left:
    st.markdown(
        f"""
        <h2 style="margin-bottom: 0;">
            Good morning, <span style="color:#ED017F;">{first_name}</span>
        </h2>
        <p style="margin-top: 0.1rem; color: #374151; font-size: 1.2rem;">
            Your year so far
        </p>
        """,
        unsafe_allow_html=True
    )

with col_right:
    st.markdown(
        f"""
        <p style="
            text-align: right;
            color: #374151;
            font-size: 0.9rem;
            margin-top: 1.6rem;
        ">
            <strong>Last refreshed:</strong> {last_refreshed}
        </p>
        """,
        unsafe_allow_html=True
    )


st.markdown(
    """
    <style>
    div[data-testid="metric-container"] {
        background-color: #f5f5f5;
        padding: 10px;
        border-radius: 8px;
        text-align: center;
        
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown(
    """
    <style>
    .stSelectbox > div[data-baseweb="select"] > div,
    .stMultiSelect > div[data-baseweb="select"] > div {
        color: black;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Load User Fig data (Target Hours)

df_user = get_sharepoint_file(
    client_id=st.secrets["sharepoint"]["client_id"],
    client_secret=st.secrets["sharepoint"]["client_secret"],
    tenant_id=st.secrets["sharepoint"]["tenant_id"],
    site_url=st.secrets["sharepoint"]["site_url"],
    file_path=st.secrets["sharepoint"]["userfig_path"])

# Load Timesheet data
df = get_sharepoint_file(
    client_id=st.secrets["sharepoint"]["client_id"],
    client_secret=st.secrets["sharepoint"]["client_secret"],
    tenant_id=st.secrets["sharepoint"]["tenant_id"],
    site_url=st.secrets["sharepoint"]["site_url"],
    file_path=st.secrets["sharepoint"]["timesheet_path"]
)

# Load Timeoff Allowance
df_allowance = get_sharepoint_file(
    client_id=st.secrets["sharepoint"]["client_id"],
    client_secret=st.secrets["sharepoint"]["client_secret"],
    tenant_id=st.secrets["sharepoint"]["tenant_id"],
    site_url=st.secrets["sharepoint"]["site_url"],
    file_path=st.secrets["sharepoint"]["allowance_path"]
)

#----------------------
# TARGET HRS CALC
#----------------------
# Convert dates
df_user["Start"] = pd.to_datetime(df_user["Start"], errors="coerce")
df_user["End"] = pd.to_datetime(df_user["End"], errors="coerce")

# Hard cap date
cap_end_date = pd.Timestamp("2025-12-31")

# Fill open-ended contracts to cap date
df_user["End"] = df_user["End"].fillna(cap_end_date)

# Cap all End dates at Dec 31, 2025
df_user["End"] = df_user["End"].clip(upper=cap_end_date)

# Calculate daily working hours
df_user["Daily_Hours"] = np.where(
    df_user["Working Hrs"] > 0,
    df_user["Working Hrs"] / 5,
    0
)



# Aggregate by employee
df_target = df_user.groupby(["Full Name", "Legal Office"], as_index=False)["Target Working Hrs"].sum()


#----------------------
# TIMESHEET CLEANING
#----------------------

df.rename(columns={
    "Employee Full Name": "Full Name", 
    "Sum of Hours": "Hours"
}, inplace=True)

# Convert Date
df["Date"] = pd.to_datetime(df["Date"])
df["Month"] = df["Date"].dt.to_period("M").astype(str)

# Force Utilization Category order
cat_order = ["Project", "Internal", "Budget PTO", "Add'l & Flex PTO"]
df["Utilization Category"] = pd.Categorical(
    df["Utilization Category"], 
    categories=cat_order, 
    ordered=True
)

# Filter timesheet to only include dates before start of this week
today = datetime.today()
start_of_week = today - timedelta(days=today.weekday())  # Monday this week
df = df[df["Date"] < start_of_week]

# Target vs Actual Comparison
df_filtered = df[df["Full Name"] == emp_name]
df_actual = df_filtered.groupby("Full Name", as_index=False)["Hours"].sum()
df_comparison = pd.merge(df_target, df_actual, on="Full Name", how="left").fillna(0)
totals_by_util = df_filtered.groupby("Utilization Category")["Hours"].sum().reset_index()

#----------------------
# METRICS
#----------------------
project_hours = totals_by_util.loc[totals_by_util["Utilization Category"] == "Project", "Hours"].sum()
internal_hours = totals_by_util.loc[totals_by_util["Utilization Category"] == "Internal", "Hours"].sum()
total_working_hours = project_hours + internal_hours
budget_pto = totals_by_util.loc[totals_by_util["Utilization Category"] == "Budget PTO", "Hours"].sum()
flex_pto = totals_by_util.loc[totals_by_util["Utilization Category"] == "Add'l & Flex PTO", "Hours"].sum()

# Calculate PTO breakdown
budget_pto_breakdown = df_filtered[df_filtered["Utilization Category"] == "Budget PTO"]
budget_pto_grouped = budget_pto_breakdown.groupby("Project No - Title")["Hours"].sum().reset_index()

# Add PTO Flex from Add'l & Flex PTO
flex_hours = df_filtered.loc[df_filtered["Utilization Category"] == "Add'l & Flex PTO", "Hours"].sum()
flex_row = pd.DataFrame({"Project No - Title": ["PTO Flex Vacation"], "Hours": [flex_hours]})
budget_pto_grouped = pd.concat([budget_pto_grouped, flex_row], ignore_index=True)
unpaid_hours = df_filtered.loc[df_filtered["Project No - Title"] == "Unpaid Time Off", "Hours"].sum()

# PTO titles order
titles_order = ["Vacation", "PTO Sick/Medical","PTO Flex Vacation", "Stat Holidays", "PTO Office Closed"]

# Merge to ensure all titles exist
all_titles_df = pd.DataFrame({"Project No - Title": titles_order})
budget_pto_grouped = pd.merge(all_titles_df, budget_pto_grouped, on="Project No - Title", how="left").fillna(0)


# Rename to match naming conventions
df_allowance.rename(columns={
    "Employee Full Name": "Full Name"
}, inplace=True)

df_allowance["Full Name"] = df_allowance["Full Name"].str.strip()
df_target["Full Name"] = df_target["Full Name"].str.strip()

df_target = df_target.merge(
    df_allowance,
    on="Full Name",
    how="left"
)

vacation_max = (
    df_target.loc[df_target["Full Name"] == emp_name, "Allowance"]
    .fillna(0)
    .iloc[0]
)

# Example max allocations per PTO type
pto_max = {
    "Vacation": vacation_max,
    "Sick/Medical": 37.5,
    "Stat Holidays": np.nan,
    "PTO Office Closed": np.nan,
    "Flex": np.nan
}

# Get target working hours for the selected employee
target_hours = df_target.loc[df_target["Full Name"] == emp_name, "Target Working Hrs"].sum()
# Calculate PTO amounts
pto_vacation = budget_pto_grouped.loc[budget_pto_grouped["Project No - Title"] == "Vacation", "Hours"].sum()
pto_sick = budget_pto_grouped.loc[budget_pto_grouped["Project No - Title"] == "PTO Sick/Medical", "Hours"].sum()
stat_holidays = budget_pto_grouped.loc[budget_pto_grouped["Project No - Title"] == "Stat Holidays", "Hours"].sum()
office_closed = budget_pto_grouped.loc[budget_pto_grouped["Project No - Title"] == "PTO Office Closed", "Hours"].sum()

combined_closed = stat_holidays + office_closed

# Calculate Adjusted Target
adjusted_target = target_hours - pto_vacation - pto_sick - combined_closed - unpaid_hours
flex_vacation = budget_pto_grouped.loc[budget_pto_grouped["Project No - Title"] == "PTO Flex Vacation", "Hours"].sum()


# PTO max values
vacation_max = pto_max["Vacation"]
sick_max = pto_max["Sick/Medical"]

vacation_used = min(pto_vacation, vacation_max)
vacation_remaining = max(vacation_max - vacation_used, 0)

sick_used = min(pto_sick, sick_max)
sick_remaining = max(sick_max - sick_used, 0)


# -------------------------
# UTILIZATION DATE WINDOWS
# -------------------------



last_month_start = pd.Timestamp("2025-12-01")
last_month_end = pd.Timestamp("2025-12-31")

ytd_start = pd.Timestamp("2025-01-01")
ytd_end = cap_end_date

df_util = df_filtered[df_filtered["Date"] <= cap_end_date]

# Last month project hours
project_last_month = df_util[
    (df_util["Utilization Category"] == "Project") &
    (df_util["Date"].between(last_month_start, last_month_end))
]["Hours"].sum()

# YTD project hours
project_ytd = df_util[
    (df_util["Utilization Category"] == "Project") &
    (df_util["Date"].between(ytd_start, ytd_end))
]["Hours"].sum()


adjusted_target_last_month = adjusted_target_for_period(
    last_month_start, last_month_end
)

adjusted_target_ytd = adjusted_target_for_period(
    ytd_start, ytd_end
)

util_last_month = (
    project_last_month / adjusted_target_last_month
    if adjusted_target_last_month > 0 else 0
)

util_ytd = (
    project_ytd / adjusted_target_ytd
    if adjusted_target_ytd > 0 else 0
)

col_left, col_right, col_charts = st.columns([0.6, 1, 0.8])

#----------------------
# Hours Worked Box
#----------------------

with col_left:
    components.html(f"""
    <div style="
        padding: 1rem;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        max-width: 400px;
        text-align: center;
        margin-top: 1rem;
        font-family: 'Source Sans Pro', 'Helvetica Neue', Helvetica, Arial, sans-serif;
    ">
        <h3 style="margin:0 0 0.25rem 0; font-weight:600; color:#111827;">Hours Worked</h3>
        <h1 style="margin:0 0 1rem 0; font-weight:700; font-size:3rem; color:#111827;">{total_working_hours:.1f}</h1>
        
        <div style="display:flex;justify-content:center; align-items:center; gap:2rem; font-family: 'Source Sans Pro', 'Helvetica Neue', Helvetica, Arial, sans-serif;">
            <div style="text-align:center;">
                <p style="margin:0; font-size:0.9rem; color:#6b7280;">Project</p>
                <p style="margin:0; font-weight:600; font-size:1.2rem; color:#111827;">{project_hours:.1f}</p>
            </div>
            <div style="font-weight:700; font-size:1.2rem; color:#111827;">+</div>
            <div style="text-align:center;">
                <p style="margin:0; font-size:0.9rem; color:#6b7280;">Internal</p>
                <p style="margin:0; font-weight:600; font-size:1.2rem; color:#111827;">{internal_hours:.1f}</p>
            </div>
        </div>
    </div>
    """, height=200)

    st.markdown(
    f"""
    <p style="
        margin-top: 0.75rem;
        font-size: 0.95rem;
        color: #374151;
    ">
        Your utilization for last month (December 2025) was
        <strong>{util_last_month:.1%}</strong>,
        and utilization YTD is
        <strong>{util_ytd:.1%}</strong>.
        Your project hours in December is {project_last_month:.1f} and target is {adjusted_target_last_month:.1f}.
        Your project hrs ytd is {project_ytd:.1f} and target is {adjusted_target_ytd:.1f}
    </p>
    """,
    unsafe_allow_html=True
    )


#----------------------
# Adjusted Target Box
#----------------------

with col_right:
    components.html(f"""
    <div style="
        padding: 1rem;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        max-width: 600px;
        text-align: center;
        margin-top: 1rem;
        font-family: 'Source Sans Pro', 'Helvetica Neue', Helvetica, Arial, sans-serif;
    ">
        <h3 style="margin:0 0 0.25rem 0; font-weight:600; color:#111827;">Adjusted Target</h3>
        <h1 style="margin:0 0 1rem 0; font-weight:700; font-size:3rem; color:#111827;">{adjusted_target:.1f}</h1>

        <div style="display:flex;justify-content:center; align-items:center; gap:1.5rem; font-family: 'Source Sans Pro', 'Helvetica Neue', Helvetica, Arial, sans-serif;">
            <div style="text-align:center;">
                <p style="margin:0; font-size:0.9rem; color:#6b7280;">Target</p>
                <p style="margin:0; font-weight:600; font-size:1.2rem; color:#111827;">{target_hours:.1f}</p>
            </div>
            <div style="font-weight:700; font-size:1.2rem; color:#111827;">-</div>
            <div style="text-align:center;">
                <p style="margin:0; font-size:0.9rem; color:#6b7280;">Vacation</p>
                <p style="margin:0; font-weight:600; font-size:1.2rem; color:#111827;">{pto_vacation:.1f}</p>
            </div>
            <div style="font-weight:700; font-size:1.2rem; color:#111827;">-</div>
            <div style="text-align:center;">
                <p style="margin:0; font-size:0.9rem; color:#6b7280;">Sick/Medical</p>
                <p style="margin:0; font-weight:600; font-size:1.2rem; color:#111827;">{pto_sick:.1f}</p>
            </div>
            <div style="font-weight:700; font-size:1.2rem; color:#111827;">-</div>
            <div style="text-align:center;">
                <p style="margin:0; font-size:0.9rem; color:#6b7280;">Stat + Office Closed</p>
                <p style="margin:0; font-weight:600; font-size:1.2rem; color:#111827;">{combined_closed:.1f}</p>
            </div>
            <div style="font-weight:700; font-size:1.2rem; color:#111827;">-</div>
            <div style="text-align:center;">
                <p style="margin:0; font-size:0.9rem; color:#6b7280;">Unpaid</p>
                <p style="margin:0; font-weight:600; font-size:1.2rem; color:#111827;">{unpaid_hours:.1f}</p>
            </div>
        </div>
    </div>
    """, height=200)

#----------------------
# Pie Charts + Addl Time Off Box
#----------------------

with col_charts:
    chart_col1, chart_col2 = st.columns([1, 0.8])
    with chart_col1:
        fig_vac = donut_chart(
            used=vacation_used,
            remaining=vacation_remaining,
            title="Vacation",
            footer=f"Max: {vacation_max:.1f} hrs"
        )
        st.pyplot(fig_vac, use_container_width=False)

    with chart_col2:
        fig_sick = donut_chart(
            used=sick_used,
            remaining=sick_remaining,
            title="Sick/Medical",
            footer="Max: 37.5 hrs"
        )
        st.pyplot(fig_sick, use_container_width=False)

    st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

    # Centered box below both charts
    components.html(f"""
    <div style="
        margin: 0 auto;
        padding: 0.75rem 1rem;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        max-width: 600px;
        text-align: center;
        font-family: 'Source Sans Pro', 'Helvetica Neue', Helvetica, Arial, sans-serif;
    ">
        <p style="
            margin: 0 0 0.5rem 0;
            font-size: 1.2rem;
            font-weight: 600;
            color: #111827;
        ">
            Additional Time Off Taken
        </p>

        <div style="display:flex; justify-content:space-between;">
            <div>
                <p style="margin:0; font-size:0.8rem; color:#6b7280;">Flex</p>
                <p style="margin:0; font-weight:600; color:#111827;">{flex_vacation:.1f}</p>
            </div>
            <div>
                <p style="margin:0; font-size:0.8rem; color:#6b7280;">Unpaid</p>
                <p style="margin:0; font-weight:600; color:#111827;">{unpaid_hours:.1f}</p>
            </div>
            <div>
                <p style="margin:0; font-size:0.8rem; color:#6b7280;">Stat Holidays</p>
                <p style="margin:0; font-weight:600; color:#111827;">{stat_holidays:.1f}</p>
            </div>
        </div>
    </div>
    """, height=120)
st.space("medium") 


#----------------------
# BAR CHART
#----------------------

agg_df = df_filtered.groupby(["Month", "Utilization Category"], as_index=False)["Hours"].sum()
totals_by_month = agg_df.groupby("Month")["Hours"].sum().reset_index()

st.subheader("Monthly Hours by Utilization Category")
bars = alt.Chart(agg_df).mark_bar().encode(
    x="Month:N",
    y="Hours:Q",
    color=alt.Color(
    "Utilization Category:N",
    scale=alt.Scale(
        domain=["Project", "Internal", "Budget PTO", "Add'l & Flex PTO"],
        range=["black", "#50005C", "#ED017F", "#F2BEDA"])),
    tooltip=["Month", "Utilization Category", "Hours"]
).properties(width=700, height=400)

text = alt.Chart(totals_by_month).mark_text(
    dy=-10,
    color="black"
).encode(
    x="Month:N",
    y="Hours:Q",
    text=alt.Text("Hours:Q")
)
st.altair_chart(bars + text)

