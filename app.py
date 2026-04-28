import streamlit as st
import pandas as pd
from datetime import datetime
from io import StringIO
from openai import OpenAI

# -------------------------
# PAGE CONFIG
# -------------------------
st.set_page_config(page_title="Bulk Post CSV Generator", layout="wide")

st.title("📊 Bulk Social Media CSV Generator")

# -------------------------
# SIDEBAR - OPENAI SETTINGS
# -------------------------
st.sidebar.header("⚙️ AI Generator")

api_key = st.sidebar.text_input("OpenAI API Key", type="password")

client = None
if api_key:
    client = OpenAI(api_key=api_key)

prompt = st.sidebar.text_area("Post Prompt", "Create engaging social media posts about AI automation")

num_posts = st.sidebar.slider("Number of Posts", 1, 20, 5)

generate_btn = st.sidebar.button("🚀 Generate Posts")

# -------------------------
# CSV STRUCTURE
# -------------------------
columns = [
    "Message", "Link", "ImageURL", "VideoURL",
    "Month(1-12)", "Day(1-31)", "Year", "Hour", "Minute(0-59)",
    "PinTitle", "Category", "Watermark", "HashtagGroup",
    "VideoThumbnailURL", "CTAGroup", "FirstComment",
    "Story(YorN)", "PinterestBoard", "AltText", "PostPreset"
]

if "data" not in st.session_state:
    st.session_state.data = pd.DataFrame(columns=columns)

# -------------------------
# AI GENERATION
# -------------------------
def generate_posts(prompt, n):
    results = []
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You generate short social media posts."},
                {"role": "user", "content": f"{prompt}. Create {n} posts."}
            ]
        )

        content = response.choices[0].message.content.split("\n")

        for line in content:
            if line.strip():
                results.append(line.strip())

    except Exception as e:
        st.error(f"Error: {e}")

    return results[:n]

if generate_btn and client:
    posts = generate_posts(prompt, num_posts)

    new_rows = []
    for p in posts:
        new_rows.append({
            "Message": p,
            "Link": "",
            "ImageURL": "",
            "VideoURL": "",
            "Month(1-12)": "",
            "Day(1-31)": "",
            "Year": "",
            "Hour": "",
            "Minute(0-59)": "",
            "PinTitle": "",
            "Category": "",
            "Watermark": "",
            "HashtagGroup": "",
            "VideoThumbnailURL": "",
            "CTAGroup": "",
            "FirstComment": "",
            "Story(YorN)": "",
            "PinterestBoard": "",
            "AltText": "",
            "PostPreset": ""
        })

    st.session_state.data = pd.concat([st.session_state.data, pd.DataFrame(new_rows)], ignore_index=True)

# -------------------------
# EDIT TABLE
# -------------------------
st.subheader("✏️ Edit Your Posts")

edited_df = st.data_editor(
    st.session_state.data,
    num_rows="dynamic",
    use_container_width=True
)

st.session_state.data = edited_df

# -------------------------
# VALIDATION
# -------------------------
st.subheader("✅ Validation")

def validate_row(row):
    errors = []

    msg_len = len(str(row["Message"]))

    limits = {
        "Facebook": 63206,
        "Instagram": 2200,
        "Bluesky": 300,
        "LinkedIn": 3000,
        "Twitter/X": 280,
        "GBP": 1500,
        "Pinterest": 500,
        "TikTok": 150
    }

    for platform, limit in limits.items():
        if msg_len > limit:
            errors.append(f"{platform} limit exceeded ({msg_len}/{limit})")

    if row["ImageURL"] and row["VideoURL"]:
        errors.append("Cannot have both ImageURL and VideoURL")

    if row["VideoURL"] and not str(row["VideoURL"]).endswith(".mp4"):
        errors.append("Video must be .mp4")

    return errors

all_errors = []

for i, row in edited_df.iterrows():
    errs = validate_row(row)
    if errs:
        all_errors.append((i, errs))

if all_errors:
    for idx, errs in all_errors:
        st.error(f"Row {idx+1}: {', '.join(errs)}")
else:
    st.success("All rows valid ✅")

# -------------------------
# DOWNLOAD CSV
# -------------------------
st.subheader("⬇️ Export CSV")

def convert_df(df):
    return df.to_csv(index=False).encode("utf-8")

csv = convert_df(edited_df)

st.download_button(
    "Download CSV",
    csv,
    "bulk_posts.csv",
    "text/csv"
)

# -------------------------
# TEMPLATE DOWNLOAD
# -------------------------
st.subheader("📄 Download Empty Template")

empty_df = pd.DataFrame(columns=columns)

st.download_button(
    "Download Template CSV",
    empty_df.to_csv(index=False),
    "template.csv",
    "text/csv"
)
