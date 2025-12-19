import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
import numpy as np
from pandas.tseries.offsets import BDay
import requests
from msal import ConfidentialClientApplication
from io import BytesIO

def get_sharepoint_csv(client_id, client_secret, tenant_id, site_url, file_path):
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

    return pd.read_csv(BytesIO(r.content))


st.set_page_config(layout = "wide")

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



emp_name = "Sumi Raveendiran"
first_name = emp_name.split(" ")[0]


from datetime import datetime, timedelta

today = datetime.today()
monday = today - timedelta(days=today.weekday())
last_refreshed = monday.strftime("%B %d, %Y")


st.markdown(
f"""
<div style="padding: 0.25rem 1rem;">
    <div style="
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
    ">
        <div>
            <h2 style="
                color: #111827;
                font-weight: 700;
                margin-bottom: 0;
            ">
                Good morning, <span style="color:#ED017F;">{first_name}</span>
            </h2>
            <h4 style="
                color: #374151;
                font-weight: 400;
                margin-top: 0;
            ">
                Your year so far
            </h4>
        </div>

        <div style="
            color: #6b7280;
            font-size: 0.9rem;
            white-space: nowrap;
        ">
            <strong>Last refreshed:</strong> {last_refreshed}
        </div>
    </div>
</div>
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

df_user = get_sharepoint_csv(
    client_id=st.secrets["sharepoint"]["client_id"],
    client_secret=st.secrets["sharepoint"]["client_secret"],
    tenant_id=st.secrets["sharepoint"]["tenant_id"],
    site_url=st.secrets["sharepoint"]["site_url"],
    file_path=st.secrets["sharepoint"]["userfig_path"])


df_user["Start"] = pd.to_datetime(df_user["Start"],errors= "coerce")
df_user["End"] = pd.to_datetime(df_user["End"], errors="coerce")

today = datetime.today()
start_of_week = today - timedelta(days=today.weekday())  # Monday this week
end_of_last_week = start_of_week - timedelta(days=1)     # Sunday last week
df_user["End"].fillna(end_of_last_week, inplace=True)

# Cap End dates at last Sunday
df_user["End"] = np.where(
    df_user["End"] > end_of_last_week,
    end_of_last_week,
    df_user["End"]
)

df_user["End"] = pd.to_datetime(df_user["End"]) 

# Calculate daily working hours
df_user["Daily_Hours"] = np.where(
    df_user["Working Hrs"] > 0,
    df_user["Working Hrs"] / 5,
    0
)

# Function to count weekdays
def weekday_hours(row):
    weekdays = pd.bdate_range(start=row["Start"], end=row["End"])
    return len(weekdays) * row["Daily_Hours"]

df_user["Target Working Hrs"] = df_user.apply(weekday_hours, axis=1)

# Aggregate by employee
df_target = df_user.groupby(["Full Name", "Legal Office"], as_index=False)["Target Working Hrs"].sum()


# Load Timesheet Export data (Actual Hours)

df = get_sharepoint_csv(
    client_id=st.secrets["sharepoint"]["client_id"],
    client_secret=st.secrets["sharepoint"]["client_secret"],
    tenant_id=st.secrets["sharepoint"]["tenant_id"],
    site_url=st.secrets["sharepoint"]["site_url"],
    file_path=st.secrets["sharepoint"]["timesheet_path"]
)



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

# Merge with target
df_comparison = pd.merge(df_target, df_actual, on="Full Name", how="left").fillna(0)


# Totals by Utilization Category (custom horizontal cards)

totals_by_util = df_filtered.groupby("Utilization Category")["Hours"].sum().reset_index()

# Compute totals
project_hours = totals_by_util.loc[totals_by_util["Utilization Category"] == "Project", "Hours"].sum()
internal_hours = totals_by_util.loc[totals_by_util["Utilization Category"] == "Internal", "Hours"].sum()
total_working_hours = project_hours + internal_hours
budget_pto = totals_by_util.loc[totals_by_util["Utilization Category"] == "Budget PTO", "Hours"].sum()
flex_pto = totals_by_util.loc[totals_by_util["Utilization Category"] == "Add'l & Flex PTO", "Hours"].sum()

# Project + Internal = Total Working Hrs
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Project Hours Worked", f"{project_hours:.1f}")
col2.metric("", "+")
col3.metric("Internal Hours Worked", f"{internal_hours:.1f}")
col4.metric("", "=")
col5.metric("Total Working Hrs", f"{total_working_hours:.1f}")

st.markdown("---")



# Second row

# Calculate PTO breakdown
budget_pto_breakdown = df_filtered[df_filtered["Utilization Category"] == "Budget PTO"]
budget_pto_grouped = budget_pto_breakdown.groupby("Project No - Title")["Hours"].sum().reset_index()

# Add PTO Flex from Add'l & Flex PTO
flex_hours = df_filtered.loc[df_filtered["Utilization Category"] == "Add'l & Flex PTO", "Hours"].sum()
flex_row = pd.DataFrame({"Project No - Title": ["PTO Flex"], "Hours": [flex_hours]})
budget_pto_grouped = pd.concat([budget_pto_grouped, flex_row], ignore_index=True)

# PTO titles order
titles_order = ["PTO Vacation", "PTO Sick/Medical","PTO Flex", "Stat Holidays", "PTO Office Closed"]

# Merge to ensure all titles exist
all_titles_df = pd.DataFrame({"Project No - Title": titles_order})
budget_pto_grouped = pd.merge(all_titles_df, budget_pto_grouped, on="Project No - Title", how="left").fillna(0)

# Example max allocations per PTO type
pto_max = {
    "PTO Vacation": 75,
    "PTO Sick/Medical": 37.5,
    "Stat Holidays": np.nan,
    "PTO Office Closed": np.nan,
    "PTO Flex": np.nan
}

# Display PTO cards
cols = st.columns(len(titles_order))
for i, row in budget_pto_grouped.iterrows():
    title = row["Project No - Title"]
    hours = row["Hours"]
    
    # Add Taken/Budget for Vacation and Sick/Medical
    if title in ["PTO Vacation", "PTO Sick/Medical"]:
        max_val = pto_max[title]
        display_val = f"{hours:.1f}/{max_val:.1f}"
    else:
        display_val = f"{hours:.1f}"
    
    cols[i].metric(label=title, value=display_val)


st.markdown("---")


# Third row

# Get target working hours for the selected employee
target_hours = df_target.loc[df_target["Full Name"] == emp_name, "Target Working Hrs"].sum()
# Calculate PTO amounts
pto_vacation = budget_pto_grouped.loc[budget_pto_grouped["Project No - Title"] == "PTO Vacation", "Hours"].sum()
pto_sick = budget_pto_grouped.loc[budget_pto_grouped["Project No - Title"] == "PTO Sick/Medical", "Hours"].sum()
stat_holidays = budget_pto_grouped.loc[budget_pto_grouped["Project No - Title"] == "Stat Holidays", "Hours"].sum()
# Calculate Adjusted Target
adjusted_target = target_hours - pto_vacation - pto_sick - stat_holidays

# Display Adjusted Target row similar to first row
col1, col2, col3, col4, col5, col6, col7, col8, col9 = st.columns(9)
col1.metric("Target Working Hours", f"{target_hours:.1f}")
col2.metric("", "-")
col3.metric("PTO Vacation", f"{pto_vacation:.1f}")
col4.metric("", "-")
col5.metric("PTO Sick/Medical", f"{pto_sick:.1f}")
col6.metric("", "-")
col7.metric("Stat Holidays", f"{stat_holidays:.1f}")
col8.metric("", "=")
col9.metric("Adjusted Target", f"{adjusted_target:.1f}")




# Monthly Bar Chart
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

