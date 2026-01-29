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
import plotly.graph_objects as go

st.set_page_config(
    layout="wide",  # makes content stretch full width
    page_title="Timesheet Dashboard"
    )

if not hasattr(st, "user") or not st.user.is_logged_in:

    st.markdown(
        """
        <style>

        
        [data-testid="stAppViewContainer"] {
            padding: 0;
        }

        [data-testid="stApp"] {
            background: none;
        }

        
        #login-button-anchor {
        margin-top: 1.5rem;
        }

        #login-button-anchor + div.stButton {
        margin-top: 0;
        }


        
        .login-container {
            position: fixed;
            inset: 0;
            background-image: url("https://raw.githubusercontent.com/Aspect-Structural-Engineers/streamlit-timesheet-dashboard/main/assets/ASPECT_Malahat.png");
            background-size: cover;
            background-position: center;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        
        .login-card {
            background: white;
            padding: 2.5rem 3rem;
            border-radius: 12px;
            width: 420px;
            text-align: center;
            box-shadow: 0 20px 40px rgba(0,0,0,0.15);
            font-family: 'Source Sans Pro', 'Helvetica Neue', Helvetica, Arial, sans-serif;

            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 1.4rem;
        }

        /* Logo */
        .login-logo {
            max-width: 140px;
            width: 100%;
            height: auto;
            margin-bottom: 1.5rem;
        }

        /* Title */
        .login-title {
            font-size: 1.45rem;
            font-weight: 700;
            color: #111827;
            margin-bottom: 1.8rem;
            white-space: nowrap;
        }

        /* Anchor for login card */
        .login-card {
            position: relative;
        }

        
        div.stButton {
            margin-top: 1rem;
            width: 100%;
        }

        /* Streamlit button overrides */
        div.stButton > button {
            background-color: white;
            color: black;
            border: 2px solid #ED017F;
            border-radius: 8px;
            padding: 0.6rem 1.2rem;
            font-size: 1rem;
            font-weight: 600;
            width: 100%;
            transition: all 0.2s ease-in-out;
        }

        div.stButton > button:hover {
            background-color: #ED017F;
            color: white;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
    """
    <div class="login-container">
        <div class="login-card">
            <img
                src="https://raw.githubusercontent.com/Aspect-Structural-Engineers/streamlit-timesheet-dashboard/main/assets/ASPECT_Full_Logo.png"
                class="login-logo"
            />
            <div class="login-title">Timesheet Dashboard</div>
            <div id="login-button-anchor"></div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

    # Centered column matching card width
    left, center, right = st.columns([3.2, 2, 2])

    with center:
        st.markdown("<br><br><br><br><br><br><br><br><br><br><br><br><br><br><br>", unsafe_allow_html=True)
        st.button("Log in with Microsoft", on_click = st.login, args=("microsoft",))
        
    st.stop()

year = st.segmented_control(
    "Year",
    options=["2025", "2026"],
    default="2026"
)

def get_sharepoint_file(client_id, client_secret, tenant_id, site_url, file_path, sheet_name = None):
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

    # Fetch file
    file_api = (
        f"https://graph.microsoft.com/v1.0/sites/{site_id}"
        f"/drive/root:/{file_path}:/content"
    )

    r = requests.get(file_api, headers=headers)
    r.raise_for_status()

    return pd.read_excel(BytesIO(r.content), engine ="openpyxl",sheet_name=sheet_name)

def render_2025_dashboard():
    
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
            0.5,        
            0.02,       
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
        # Target hours in period
        target = (
            df_user[df_user["Full Name"] == emp_name]
            .apply(target_hours_in_period, axis=1, args=(start_date, end_date))
            .sum()
        )

        # PTO taken in period
        pto = df_util[
            (df_util["Date"].between(start_date, end_date)) &
            (df_util["Project No - Title"].isin([
                "Vacation",
                "PTO Office Closed",
                "Stat Holidays",
                "Unpaid Time Off",
                "PTO Sick/Medical"
            ]))
        ]["Hours"].sum()

        return max(target - pto, 0)

    def weekday_hours(row):
        weekdays = pd.bdate_range(start=row["Start"], end=row["End"])
        return len(weekdays) * row["Daily_Hours"]


    # Load data
    df_user = get_sharepoint_file(
        client_id=st.secrets["sharepoint"]["client_id"],
        client_secret=st.secrets["sharepoint"]["client_secret"],
        tenant_id=st.secrets["sharepoint"]["tenant_id"],
        site_url=st.secrets["sharepoint"]["site_url"],
        file_path=st.secrets["sharepoint"]["userfig_path_2025"])


    df = get_sharepoint_file(
        client_id=st.secrets["sharepoint"]["client_id"],
        client_secret=st.secrets["sharepoint"]["client_secret"],
        tenant_id=st.secrets["sharepoint"]["tenant_id"],
        site_url=st.secrets["sharepoint"]["site_url"],
        file_path=st.secrets["sharepoint"]["timesheet_path_2025"]
    )

    df_allowance = get_sharepoint_file(
        client_id=st.secrets["sharepoint"]["client_id"],
        client_secret=st.secrets["sharepoint"]["client_secret"],
        tenant_id=st.secrets["sharepoint"]["tenant_id"],
        site_url=st.secrets["sharepoint"]["site_url"],
        file_path=st.secrets["sharepoint"]["allowance_path_2025"]
    )

    logged_in_email = st.user.email
    user_info = df_user[df_user["Email"].str.lower() == logged_in_email.lower()]

    if not user_info.empty:
        emp_name = user_info.iloc[0]["Full Name"]
    else:
        emp_name = "Unknown User"
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
                Your 2025 CMAP Recap:
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

    df_user["Target Working Hrs (Contract)"] = df_user.apply(weekday_hours, axis=1)


    # Aggregate by employee
    df_target = df_user.groupby(["Full Name", "Legal Office"], as_index=False)["Target Working Hrs (Contract)"].sum()

    df_util_target = (
        df_user
        .groupby("Full Name", as_index=False)
        .agg({"Utilization Target": "mean"})
    )

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

    util_target = (
        df_util_target.loc[df_util_target["Full Name"] == emp_name, "Utilization Target"]
        .fillna(0)
        .iloc[0]
    )

    #  max allocations per PTO type
    pto_max = {
        "Vacation": vacation_max,
        "Sick/Medical": 37.5,
        "Stat Holidays": np.nan,
        "PTO Office Closed": np.nan,
        "Flex": np.nan
    }

    # Get target working hours for the selected employee
    target_hours = df_target.loc[df_target["Full Name"] == emp_name, "Target Working Hrs (Contract)"].sum()
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

    col_metrics, col_charts = st.columns([1.6, 0.8])

    #----------------------
    # Hours Worked Box
    #----------------------
    with col_metrics:
        col_left, col_right = st.columns([0.6, 1])
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
                <h3 style="margin:0 0 0.25rem 0; font-weight:600; color:#111827;">Adjusted Baseline</h3>
                <h1 style="margin:0 0 1rem 0; font-weight:700; font-size:3rem; color:#111827;">{adjusted_target:.1f}</h1>

                <div style="display:flex;justify-content:center; align-items:center; gap:1.5rem; font-family: 'Source Sans Pro', 'Helvetica Neue', Helvetica, Arial, sans-serif;">
                    <div style="text-align:center;">
                        <p style="margin:0; font-size:0.9rem; color:#6b7280;">Baseline</p>
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

    # ----------------------
    # Bottom Summary Row
    # ----------------------

    util_left, util_right = st.columns([1.6, 0.8])

    with util_left:
        components.html(
            f"""
            <div style="
                padding: 0.75rem 1rem;
                border: 1px solid #e5e7eb;
                border-radius: 10px;
                font-size: 0.95rem;
                color: #374151;
                font-family: 'Source Sans Pro', 'Helvetica Neue', Helvetica, Arial, sans-serif;
            ">
                <p style="margin:0;">
                    Your utilization for last month (December 2025) was
                    <strong>{util_last_month:.1%}</strong>,
                    and utilization YTD is
                    <strong><span style="color:#ED017F;">{util_ytd:.1%}</span></strong>. 
                    Your utilization target is 
                    <strong><span style="color:#ED017F;">{util_target:.1%}</span></strong>
                </p>
                <p style="margin:0.4rem 0 0 0;">
                    Project hours in December:
                    <strong>{project_last_month:.1f}</strong>
                    &nbsp;/&nbsp;
                    Baseline:
                    <strong>{adjusted_target_last_month:.1f}</strong>
                </p>
                <p style="margin:0.25rem 0 0 0;">
                    Project hours YTD:
                    <strong>{project_ytd:.1f}</strong>
                    &nbsp;/&nbsp;
                    Baseline:
                    <strong>{adjusted_target_ytd:.1f}</strong>
                </p>
            </div>
            """,
            height=120
        )

    with util_right:
        components.html(
            f"""
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
            """,
            height=120
        )


    #----------------------
    # BAR CHART
    #----------------------

    agg_df = df_filtered.groupby(["Month", "Utilization Category"], as_index=False)["Hours"].sum()

    #agg_df = df_filtered.groupby(["Month", "Utilization Category"], as_index=False)["Hours"].sum()
    # Get totals by month for text labels

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


    pass


def render_2026_dashboard():
    st.markdown(
        """
        <style>
        /* Main responsive content container */
        .app-container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 1.25rem 1.25rem;
            width: 100%;
        }

        /* Mobile spacing */
        @media (max-width: 768px) {
            .app-container {
                padding: 1rem 0.75rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        """
        <style>
        .info-tooltip {
            font-size: 0.75rem;
            font-weight: 400;
            color: #6B7280;
            margin-left: 0.25rem;
            vertical-align: middle;
            cursor: help;
        }
        .info-tooltip:hover {
            color: #374151;              /* slightly darker on hover */
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown('<div class="app-container">', unsafe_allow_html=True)


    st.set_page_config(
            layout="wide",  # makes content stretch full width
            page_title="Timesheet Dashboard"
            )

    #st.markdown(
    #        """
    #        <style>
    #        /* Remove Streamlit top padding */
    #        .block-container {
    #            padding-top: 1rem !important;
    #        }
    #        </style>
    #        """,
    #        unsafe_allow_html=True
    #    )

    

    def target_hours_in_period(row, period_start, period_end):
            start = max(row["Start"], period_start)
            end = min(row["End"], period_end)

            if start > end:
                return 0

            weekdays = pd.bdate_range(start=start, end=end)
            return len(weekdays) * row["Daily_Hours"]

    def adjusted_target_for_period(start_date, end_date):
            # Target hours in period
            target = (
                df_user[df_user["Full Name"] == emp_name]
                .apply(target_hours_in_period, axis=1, args=(start_date, end_date))
                .sum()
            )

            # PTO taken in period
            pto = df_util[
                (df_util["Date"].between(start_date, end_date)) &
                (df_util["Project No - Title"].isin([
                    "Vacation",
                    "PTO Office Closed",
                    "Stat Holidays",
                    "Unpaid Time Off",
                    "PTO Sick/Medical"
                ]))
            ]["Hours"].sum()

            return max(target - pto, 0)

    def weekday_hours(row):
            weekdays = pd.bdate_range(start=row["Start"], end=row["End"])
            return len(weekdays) * row["Daily_Hours"]


    def title_info_annotation(text, x=0.63):
            return dict(
                text="ⓘ",
                x=x,
                y=1.02,
                xref="paper",
                yref="paper",
                showarrow=False,
                font=dict(size=14, color="#6B7280"),
                hovertext=text,
                hoverlabel=dict(
                    bgcolor="white",
                    font_size=12,
                    font_color="#111827"
                ),
            )


    def donut_chart_plotly(used, remaining, title, footer, annotation_text):
            fig = go.Figure(
                data=[
                    go.Pie(
                        values=[used, remaining],
                        labels=["Used", "Remaining"],
                        hole=0.72,
                        direction="clockwise",
                        rotation = 90,
                        marker=dict(
                            colors=["#ED017F", "#F7B3D6"]
                        ),
                        textinfo="none",
                        hovertemplate="%{label}: %{value:.1f} hrs<extra></extra>",
                    )
                ]
            )

            fig.update_layout(
                title=dict(
                    text=title,
                    y=1,
                    x=0.5,
                    xanchor="center",
                    yanchor="top",
                    font=dict(size=25, color="#111827"),
                ),
                annotations=[
                    title_info_annotation(annotation_text),
                    dict(
                        text=f"<b>{used:.1f}</b>",
                        x=0.5,
                        y=0.5,
                        font=dict(size=25, color="#111827"),
                        showarrow=False,
                    ),
                    dict(
                        text=footer,
                        x=0.5,
                        y=-0.25,
                        font=dict(size=15, color="#6b7280"),
                        showarrow=False,
                    ),
                ],
                showlegend=False,
                margin=dict(t=40, b=35, l=0, r=0),
                height=240,
            )

            return fig


    def donut_chart_plotly_vacation(
            used,
            remaining,
            booked,
            title,
            footer,
            annotation_text
        ):
            fig = go.Figure(
                data=[
                    go.Pie(
                        values=[used, booked, remaining],
                        labels=["Used", "Booked", "Remaining"],
                        hole=0.72,
                        direction="clockwise",
                        rotation = 90,
                        marker=dict(
                            colors=[
                                "#ED017F",   
                                "#F7B3D6",
                                "#ED017F",    
                            ],

                            pattern=dict(
                                shape=["", "/", ""],   # <-- pattern only on Future Booked
                                fgcolor="#ED017F",
                                solidity=0.5
                            )
                        ),
                        textinfo="none",
                        hovertemplate="%{label}: %{value:.1f} hrs<extra></extra>",
                    )
                ]
            )

            fig.update_layout(
                title=dict(
                    text=title,
                    y=1,
                    x=0.5,
                    xanchor="center",
                    yanchor="top",
                    font=dict(size=25, color="#111827"),
                ),
                annotations=[
                    title_info_annotation(annotation_text),
                    dict(
                        text=f"<b>{used + booked:.1f}</b>",
                        x=0.5,
                        y=0.5,
                        font=dict(size=25, color="#111827"),
                        showarrow=False,
                    ),
                    dict(
                        text=footer,
                        x=0.5,
                        y=-0.25,
                        font=dict(size=15, color="#6b7280"),
                        showarrow=False,
                    ),
                ],
                showlegend=False,
                margin=dict(t=40, b=35, l=0, r=0),
                height=240,
            )

            return fig
    
    df_user = get_sharepoint_file(
        client_id=st.secrets["sharepoint"]["client_id"],
        client_secret=st.secrets["sharepoint"]["client_secret"],
        tenant_id=st.secrets["sharepoint"]["tenant_id"],
        site_url=st.secrets["sharepoint"]["site_url"],
        file_path=st.secrets["sharepoint"]["userfig_path_2026"],
        sheet_name="PQ")

    df = get_sharepoint_file(
        client_id=st.secrets["sharepoint"]["client_id"],
        client_secret=st.secrets["sharepoint"]["client_secret"],
        tenant_id=st.secrets["sharepoint"]["tenant_id"],
        site_url=st.secrets["sharepoint"]["site_url"],
        file_path=st.secrets["sharepoint"]["timesheet_path_2026"],
        sheet_name="PQ"
    )

    df_allowance = get_sharepoint_file(
        client_id=st.secrets["sharepoint"]["client_id"],
        client_secret=st.secrets["sharepoint"]["client_secret"],
        tenant_id=st.secrets["sharepoint"]["tenant_id"],
        site_url=st.secrets["sharepoint"]["site_url"],
        file_path=st.secrets["sharepoint"]["allowance_path_2026"],
        sheet_name="PQ"
    )

    logged_in_email = st.user.email
    user_info = df_user[df_user["Email"].str.lower() == logged_in_email.lower()]

    if not user_info.empty:
        emp_name = user_info.iloc[0]["Full Name"]
    else:
        emp_name = "Unknown User"
    first_name = emp_name.split(" ")[0]

        # ----------------------
        # LOCAL TEST DATA (2026)
        # ----------------------

    today = datetime.today()
    monday = today - timedelta(days=today.weekday())
    last_refreshed = monday.strftime("%B %d, %Y")

    excluded_categories = ["Budget PTO", "Add'l & Flex PTO"]

    df_emp_worked = df[
        (df["Employee Full Name"] == emp_name) &
        (~df["Utilization Category"].isin(excluded_categories))
    ]
    timesheet_date = df_emp_worked["Date"].max()
    timesheet_date_week = df_emp_worked["Date"].max() - timedelta(days=timesheet_date.weekday())
    timesheet_date_str = timesheet_date_week.strftime("%B %d, %Y")

    is_stale = timesheet_date_week != monday

    timesheet_color = "#DC2626" if is_stale else "#374151"   # red vs normal
    timesheet_weight = "600" if is_stale else "400"


    col_left, col_right = st.columns([3, 1])

    with col_left:
        st.markdown(
            f"""
            <h2 style="margin-bottom: 0;">
                Good morning, <span style="color:#ED017F;">{first_name}</span>
            </h2>
            <p style="margin-top: 0.1rem; color: #374151; font-size: 1.2rem;">
                Your year so far:
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
            ">
                <strong>Last refreshed:</strong> {last_refreshed}
                    <span
                        class="info-tooltip"
                        title="The data refresh date. Timesheet data is refreshed weekly on Mondays. Your Baseline is updated till the Friday before the refresh."
                        style="vertical-align: super;" 
                    > ⓘ</span>
            </p>
            <p style="
                text-align: right;
                color: {timesheet_color};
                font-size: 0.9rem;
                font-weight: {timesheet_weight};
            ">
                <strong>Timesheet Week:</strong> {timesheet_date_str}
                <span
                    class="info-tooltip"
                    title="The most recent timesheet week included in this dashboard. If this date is before the last refreshed date, your timesheet may have missing entries, hence the red color. Please ensure your timesheet is up to date."
                    style="vertical-align: super;"
                > ⓘ</span>
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


    #----------------------
    # TARGET HRS CALC
    #----------------------
    # Convert dates
    df_user["Start"] = pd.to_datetime(df_user["Start"], errors="coerce")
    df_user["End"] = pd.to_datetime(df_user["End"], errors="coerce")

    # Hard cap date
    cap_end_date = monday-timedelta(days=1)  # Sunday this week

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

    df_user["Target Working Hrs (Contract)"] = df_user.apply(weekday_hours, axis=1)


    # Aggregate by employee
    df_target = df_user.groupby(["Full Name", "Legal Office"], as_index=False)["Target Working Hrs (Contract)"].sum()

    df_util_target = (
        df_user
        .groupby("Full Name", as_index=False)
        .agg({"Utilization Target": "mean"})
    )

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
    df_future = df[df["Date"] >= start_of_week].copy()
    df = df[df["Date"] < start_of_week]

    # Target vs Actual Comparison
    df_filtered = df[df["Full Name"] == emp_name]
    df_actual = df_filtered.groupby("Full Name", as_index=False)["Hours"].sum()
    df_comparison = pd.merge(df_target, df_actual, on="Full Name", how="left").fillna(0)
    totals_by_util = df_filtered.groupby("Utilization Category")["Hours"].sum().reset_index()

    future_vacation = df_future[
        (df_future["Full Name"] == emp_name) &
        (df_future["Project No - Title"].isin([
            "Vacation",
            "PTO Flex Vacation"
        ]))
    ]

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

    prod_hours = df_filtered.loc[df_filtered["Project No - Title"] == "Professional Development", "Hours"].sum()
    future_vacation_hours = future_vacation.loc[future_vacation["Project No - Title"] == "Vacation","Hours"].sum()
    future_flex_hours = future_vacation.loc[future_vacation["Project No - Title"] == "PTO Flex Vacation","Hours"].sum()

    # PTO titles order
    titles_order = ["Vacation", "PTO Sick/Medical","PTO Flex Vacation", "Stat Holidays", "PTO Office Closed"]

    # Merge to ensure all titles exist
    all_titles_df = pd.DataFrame({"Project No - Title": titles_order})
    budget_pto_grouped = pd.merge(all_titles_df, budget_pto_grouped, on="Project No - Title", how="left").fillna(0)


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

    util_target = (
        df_util_target.loc[df_util_target["Full Name"] == emp_name, "Utilization Target"]
        .fillna(0)
        .iloc[0]
    )

    #  max allocations per PTO type
    pto_max = {
        "Vacation": vacation_max,
        "Sick/Medical": 37.5,
        "Stat Holidays": np.nan,
        "PTO Office Closed": np.nan,
        "Flex": np.nan
    }

    # Get target working hours for the selected employee
    target_hours = df_target.loc[df_target["Full Name"] == emp_name, "Target Working Hrs (Contract)"].sum()
    # Calculate PTO amounts
    pto_vacation = budget_pto_grouped.loc[budget_pto_grouped["Project No - Title"] == "Vacation", "Hours"].sum()
    pto_sick = budget_pto_grouped.loc[budget_pto_grouped["Project No - Title"] == "PTO Sick/Medical", "Hours"].sum() + budget_pto_grouped.loc[budget_pto_grouped["Project No - Title"] == "Bereavement", "Hours"].sum()
    stat_holidays = budget_pto_grouped.loc[budget_pto_grouped["Project No - Title"] == "Stat Holidays", "Hours"].sum()
    office_closed = budget_pto_grouped.loc[budget_pto_grouped["Project No - Title"] == "PTO Office Closed", "Hours"].sum()
    combined_closed = stat_holidays + office_closed

    # Calculate Adjusted Target
    adjusted_target = target_hours - pto_vacation - pto_sick - combined_closed - unpaid_hours
    flex_vacation = budget_pto_grouped.loc[budget_pto_grouped["Project No - Title"] == "PTO Flex Vacation", "Hours"].sum() + future_flex_hours


    # PTO max values
    vacation_max = pto_max["Vacation"]
    sick_max = pto_max["Sick/Medical"]

    vacation_used = min(pto_vacation, vacation_max)
    vacation_remaining = max(vacation_max - vacation_used - future_vacation_hours, 0)

    sick_used = min(pto_sick, sick_max)
    sick_remaining = max(sick_max - sick_used, 0)


    # -------------------------
    # UTILIZATION DATE WINDOWS
    # -------------------------

    # Last month relative to current data cutoff
    last_month_end = cap_end_date.replace(day=1) - pd.Timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)


    ytd_start = pd.Timestamp("2026-01-01")
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

    delta_hours =  total_working_hours  - adjusted_target
    last_month_label = last_month_start.strftime("%B %Y")

    #----------------------
    # Hours Worked Box
    #----------------------

    r1_c1, r1_c2, r1_c3 = st.columns(3, gap="large")

    with r1_c1:
            components.html(f"""
            <div style="
                width: 100%;
                padding: 1rem;
                border: 1px solid #e5e7eb;
                border-radius: 10px;
                box-sizing: border-box;
                text-align: center;
                margin-top: 0rem;
                margin-bottom: 0rem;
                font-family: 'Source Sans Pro', 'Helvetica Neue', Helvetica, Arial, sans-serif;
            ">
                <h3 style="margin:0 0 0.25rem 0; font-weight:600; color:#111827;">Hours Worked<span
                    class="info-tooltip"
                    title="Your total hours worked. Only includes Project and Internal hours."
                    style="
                        font-size: 1rem;
                        font-weight: 400;
                        color: #6B7280;
                        vertical-align: super;"        
                > ⓘ</span></h3>
                            
                <h1 style="margin:0 0 1rem 0; font-weight:700; font-size:3rem; color:#111827;">{total_working_hours:.1f}</h1>
                <div style="
                display:grid;
                grid-template-columns: auto auto auto;
                gap:1.5rem;
                justify-content:center;
                ">
                
                    <div style="display:flex;justify-content:center; align-items:center; gap:2rem; font-family: 'Source Sans Pro', 'Helvetica Neue', Helvetica, Arial, sans-serif;">
                        <div style="text-align:center;">
                            <p style="margin:0; font-size:0.9rem; color:#6b7280;">Project</p>
                            <p style="margin:0; font-weight:600; font-size:1.2rem; color:#111827;">{project_hours:.1f}</p>
                        </div>
                        <div style="font-weight:700; font-size:1.2rem; color:#111827;">+</div>
                        <div style="text-align:center;">
                            <p style="margin:0; font-size:0.9rem; color:#6b7280;">Internal</p>
                            <p style="margin:0; font-weight:600; font-size :1.2rem; color:#111827;">{internal_hours:.1f}</p>
                        </div>
                    </div>
                </div>
            </div>
            """,height=200)
    
    #----------------------
    # Adjusted Target Box
    #----------------------

    with r1_c2:
            components.html(f"""
            <div style="
                width: 100%;
                padding: 1rem;
                border: 1px solid #e5e7eb;
                border-radius: 10px;
                box-sizing: border-box;
                text-align: center;
                margin-top: 0rem;
                margin-bottom: 0rem;
                font-family: 'Source Sans Pro', 'Helvetica Neue', Helvetica, Arial, sans-serif;
            ">
                <h3 style="margin:0 0 0.25rem 0; font-weight:600; color:#111827;">Adjusted Baseline<span
                    class="info-tooltip"
                    title="Your adjusted baseline. Baseline is calculated per your weekly working hours, minus any budgeted time off taken (vacation, sick, stat, unpaid). Stat includes both statutory holidays and winter break time. Sick includes bereavment."
                    style="
                        font-size: 1rem;
                        font-weight: 400;
                        color: #6B7280;
                        vertical-align: super;    "        
                > ⓘ</span></h3>
                <h1 style="margin:0 0 1rem 0; font-weight:700; font-size:3rem; color:#111827;">{adjusted_target:.1f}</h1>

                <div style="
                display:grid;
                grid-template-columns: repeat(auto-fit, minmax(90px, 1fr));
                gap:1rem;
                ">

                    <div style="display:flex;justify-content:center; align-items:center; gap:1.5rem; font-family: 'Source Sans Pro', 'Helvetica Neue', Helvetica, Arial, sans-serif;">
                        <div style="text-align:center;">
                            <p style="margin:0; font-size:0.9rem; color:#6b7280;">Baseline</p>
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
                            <p style="margin:0; font-size:0.9rem; color:#6b7280;">Stat</p>
                            <p style="margin:0; font-weight:600; font-size:1.2rem; color:#111827;">{combined_closed:.1f}</p>
                        </div>
                        <div style="font-weight:700; font-size:1.2rem; color:#111827;">-</div>
                        <div style="text-align:center;">
                            <p style="margin:0; font-size:0.9rem; color:#6b7280;">Unpaid</p>
                            <p style="margin:0; font-weight:600; font-size:1.2rem; color:#111827;">{unpaid_hours:.1f}</p>
                        </div>
                    </div>
                </div>
            </div>
            """,height=200)

    with r1_c3:
            components.html(f"""
            <div style="
                width: 100%;
                padding: 1rem;
                border: 1px solid #e5e7eb;
                border-radius: 10px;
                box-sizing: border-box;
                text-align: center;
                margin-top: 0rem;
                margin-bottom: 0rem;
                font-family: 'Source Sans Pro', 'Helvetica Neue', Helvetica, Arial, sans-serif;
            ">
            <h3 style="margin:0 0 0.25rem 0; font-weight:600; color:#111827;">Hours ± Baseline<span
                    class="info-tooltip"
                    title="If you don't want to do the math. If your timesheet is up to date, this shows how many hours you've worked above or below your adjusted baseline."
                    style="
                        font-size: 1rem;
                        font-weight: 400;
                        color: #6B7280;
                        vertical-align: super;    "        
                > ⓘ</span></h3>
            <h1 style="margin:0 0 1rem 0; font-weight:700; font-size:3rem; color:#111827;">{delta_hours:.1f}</h1>                 
                <div style="display:flex;justify-content:center; align-items:center; gap:1.5rem; font-family: 'Source Sans Pro', 'Helvetica Neue', Helvetica, Arial, sans-serif;">
                        <div style="text-align:center;">
                            <p style="margin:0; font-size:0.9rem; color:#6b7280;">Hours Worked</p>
                            <p style="margin:0; font-weight:600; font-size:1.2rem; color:#111827;">{total_working_hours:.1f}</p>
                        </div>
                        <div style="font-weight:700; font-size:1.2rem; color:#111827;">-</div>
                        <div style="text-align:center;">
                            <p style="margin:0; font-size:0.9rem; color:#6b7280;">Adjusted Baseline</p>
                            <p style="margin:0; font-weight:600; font-size:1.2rem; color:#111827;">{adjusted_target:.1f}</p>
                        </div>
                </div>
            </div>
            """,height=200)

    #st.markdown("<div style='margin-top:-0.75rem'></div>", unsafe_allow_html=True)

    r2_c1, r2_c2, r2_c3 = st.columns(3, gap="small")
    #----------------------
    # Pie Charts + Addl Time Off Box
    #----------------------

    with r2_c1:
        fig_pd = donut_chart_plotly(
            used=prod_hours,
            remaining=30 - prod_hours,
            title="PD",
            footer="Max: 30 hrs",
            annotation_text= "Professional development time you have used."
        )
        st.plotly_chart(fig_pd, use_container_width=True, config ={"displayModeBar": False})

    with r2_c2:
        fig_vac = donut_chart_plotly_vacation(
        used=vacation_used,
        remaining=vacation_remaining,
        booked=future_vacation_hours,
        title="Vacation",
        footer=f"Max: {vacation_max:.1f} hrs",
        annotation_text= "Vacation time you have used and booked. Future booked time is shown with a pattern."
    )
        st.plotly_chart(fig_vac, use_container_width=True, config ={"displayModeBar": False})

    with r2_c3:
        fig_sick = donut_chart_plotly(
            used=sick_used,
            remaining=sick_remaining,
            title="Sick / Medical",
            footer="Max: 37.5 hrs",
            annotation_text= "Sick time you have used."
        )
        st.plotly_chart(fig_sick, use_container_width=True, config ={"displayModeBar": False})

    # ----------------------
    # Bottom Summary Row
    # ----------------------
    util_left, util_right = st.columns([1.6, 0.8])

    with util_left:
        components.html(
            f"""
            <div style="
                width: 100%;
                box-sizing: border-box;
                padding: 0.75rem 1rem;
                border: 1px solid #e5e7eb;
                border-radius: 10px;
                font-size: 0.95rem;
                color: #374151;
                font-family: 'Source Sans Pro', 'Helvetica Neue', Helvetica, Arial, sans-serif;
            ">
                <p style="margin:0;">
                    Your utilization for last month ({last_month_label}) was
                    <strong>{util_last_month:.1%}</strong>,
                    and utilization YTD is
                    <strong><span style="color:#ED017F;">{util_ytd:.1%}</span></strong>. 
                    Your utilization target is 
                    <strong><span style="color:#ED017F;">{util_target:.1%}</span><span
                    class="info-tooltip"
                    title="Your utilization vs target. If you take flex time off, your utilization may be impacted as flex time is not included in hours worked, but is included in your baseline."
                    style="
                        font-size: 1rem;
                        font-weight: 400;
                        color: #6B7280;
                        vertical-align: super;    "        
                > ⓘ</span></strong>
                </p>
                <p style="margin:0.4rem 0 0 0;">
                    Project hours in December:
                    <strong>{project_last_month:.1f}</strong>
                    &nbsp;/&nbsp;
                    Baseline:
                    <strong>{adjusted_target_last_month:.1f}</strong>
                </p>
                <p style="margin:0.25rem 0 0 0;">
                    Project hours YTD:
                    <strong>{project_ytd:.1f}</strong>
                    &nbsp;/&nbsp;
                    Baseline:
                    <strong>{adjusted_target_ytd:.1f}</strong>
                </p>
            </div>
            """,
            height=120
        )

    with util_right:
        components.html(
            f"""
            <div style="
                margin: 0 auto;
                padding: 0.75rem 1rem;
                border: 1px solid #e5e7eb;
                border-radius: 10px;
                text-align: center;
                font-family: 'Source Sans Pro', 'Helvetica Neue', Helvetica, Arial, sans-serif;
            ">
                <p style="
                    margin: 0 0 0.5rem 0;
                    font-size: 1.2rem;
                    font-weight: 600;
                    color: #111827;
                ">
                    Additional Time Off<span
                    class="info-tooltip"
                    title="Additional Time off. Includes flex, unpaid, and stat + winter break."
                    style="
                        font-size: 1rem;
                        font-weight: 400;
                        color: #6B7280;
                        vertical-align: super;    "        
                > ⓘ</span>
                </p>

                <div style="display:flex; justify-content:space-between;">
                    <div>
                        <p style="margin:0; font-size:0.8rem; color:#6b7280;">Flex (Used + Booked)</p>
                        <p style="margin:0; font-weight:600; color:#111827;">{flex_vacation:.1f}</p>
                    </div>
                    <div>
                        <p style="margin:0; font-size:0.8rem; color:#6b7280;">Unpaid</p>
                        <p style="margin:0; font-weight:600; color:#111827;">{unpaid_hours:.1f}</p>
                    </div>
                    <div>
                        <p style="margin:0; font-size:0.8rem; color:#6b7280;">Stat + Winter Break</p>
                        <p style="margin:0; font-weight:600; color:#111827;">{combined_closed:.1f}</p>
                    </div>
                </div>
            </div>
            """,
            height=120
        )

    agg_df = df_filtered.groupby(["Month", "Utilization Category"], as_index=False)["Hours"].sum()

    #agg_df = df_filtered.groupby(["Month", "Utilization Category"], as_index=False)["Hours"].sum()
    # Get totals by month for text labels

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

    pass

if year == "2025":
    render_2025_dashboard()
else:
    render_2026_dashboard()



