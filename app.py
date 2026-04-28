import streamlit as st
import pandas as pd
import csv
import io
import json
import anthropic
from datetime import datetime

st.set_page_config(
    page_title="Bulk Post Creator",
    page_icon="📢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stSidebar"] { background: #0f1117; }
[data-testid="stSidebar"] * { color: #e0e0e0 !important; }
[data-testid="stSidebar"] .stTextArea textarea,
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stNumberInput input {
    background: #1e2130 !important;
    color: #fff !important;
    border: 1px solid #333 !important;
    border-radius: 8px;
}
[data-testid="stSidebar"] .stButton button {
    background: #185FA5;
    color: white;
    border: none;
    border-radius: 8px;
    width: 100%;
}
[data-testid="stSidebar"] .stButton button:hover { background: #0C447C; }
div[data-testid="stMetricValue"] { font-size: 2rem; font-weight: 600; }
.status-scheduled { background:#dbeafe; color:#1e40af; padding:2px 10px; border-radius:12px; font-size:12px; font-weight:600; }
.status-queued    { background:#dcfce7; color:#166534; padding:2px 10px; border-radius:12px; font-size:12px; font-weight:600; }
.status-empty     { background:#fee2e2; color:#991b1b; padding:2px 10px; border-radius:12px; font-size:12px; font-weight:600; }
.ai-badge { background:#ede9fe; color:#5b21b6; padding:2px 8px; border-radius:12px; font-size:11px; font-weight:600; margin-left:6px; }
</style>
""", unsafe_allow_html=True)

# ── Constants ───────────────────────────────────────────────────────────────
PLATFORM_LIMITS = {
    "Facebook": 63206,
    "Instagram": 2200,
    "Twitter/X": 280,
    "LinkedIn": 3000,
    "Bluesky": 300,
    "Pinterest": 500,
    "Google My Business": 1500,
    "TikTok": 150,
}

CSV_COLUMNS = [
    "Message", "Link", "ImageURL", "VideoURL",
    "Month(1-12)", "Day(1-31)", "Year", "Hour", "Minute(0-59)",
    "PinTitle", "Category", "Watermark", "HashtagGroup",
    "VideoThumbnailURL", "CTAGroup", "FirstComment",
    "Story(YorN)", "PinterestBoard", "AltText", "PostPreset"
]

# ── Session state defaults ───────────────────────────────────────────────────
if "posts" not in st.session_state:
    st.session_state.posts = []
if "edit_idx" not in st.session_state:
    st.session_state.edit_idx = None
if "ai_status" not in st.session_state:
    st.session_state.ai_status = ""
if "selected_platforms" not in st.session_state:
    st.session_state.selected_platforms = ["Facebook", "Instagram"]

# ── Helpers ──────────────────────────────────────────────────────────────────
def empty_post():
    return {c: "" for c in CSV_COLUMNS} | {"_ai": False}

def get_status(post):
    if not post.get("Message", "").strip():
        return "empty"
    if all(post.get(f) for f in ["Month(1-12)", "Day(1-31)", "Year", "Hour"]):
        return "scheduled"
    return "queued"

def posts_to_df():
    rows = []
    for p in st.session_state.posts:
        rows.append({c: p.get(c, "") for c in CSV_COLUMNS})
    return pd.DataFrame(rows, columns=CSV_COLUMNS)

def df_to_posts(df):
    posts = []
    for _, row in df.iterrows():
        p = {c: str(row.get(c, "") if pd.notna(row.get(c, "")) else "") for c in CSV_COLUMNS}
        p["_ai"] = False
        posts.append(p)
    return posts

def get_csv_bytes():
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for p in st.session_state.posts:
        writer.writerow({c: p.get(c, "") for c in CSV_COLUMNS})
    return buf.getvalue().encode()

def get_template_bytes():
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    writer.writerow({
        "Message": "Your post message here",
        "Link": "https://yoursite.com",
        "ImageURL": "https://image.jpg",
        "VideoURL": "",
        "Month(1-12)": "", "Day(1-31)": "", "Year": "", "Hour": "", "Minute(0-59)": "",
        "PinTitle": "", "Category": "", "Watermark": "Default", "HashtagGroup": "",
        "VideoThumbnailURL": "", "CTAGroup": "", "FirstComment": "",
        "Story(YorN)": "", "PinterestBoard": "", "AltText": "", "PostPreset": ""
    })
    return buf.getvalue().encode()

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📢 Post Studio")
    st.markdown("**Bulk CSV Creator**")
    st.divider()

    # ── AI Generator ────────────────────────────────────────────────────────
    st.markdown("### ✨ AI Post Generator")
    api_key = st.text_input("Anthropic API Key", type="password", placeholder="sk-ant-...", help="Your Anthropic API key")
    ai_prompt = st.text_area(
        "Describe your posts",
        placeholder="e.g. Summer sale on sneakers, fun energetic tone, include a CTA to shop now...",
        height=100
    )
    ai_count = st.number_input("Number of posts to generate", min_value=1, max_value=20, value=3)

    # Platform selector for AI length guidance
    st.markdown("**Target platforms**")
    selected = []
    cols = st.columns(2)
    for i, (plat, limit) in enumerate(PLATFORM_LIMITS.items()):
        default = plat in st.session_state.selected_platforms
        if cols[i % 2].checkbox(plat, value=default, key=f"plat_{plat}"):
            selected.append(plat)
    st.session_state.selected_platforms = selected

    if selected:
        min_limit = min(PLATFORM_LIMITS[p] for p in selected)
        tightest = min(selected, key=lambda p: PLATFORM_LIMITS[p])
        st.caption(f"⚠️ Tightest limit: **{tightest}** → {min_limit:,} chars")
        with st.expander("Character limits"):
            for p in sorted(selected, key=lambda p: PLATFORM_LIMITS[p]):
                st.markdown(f"- **{p}**: {PLATFORM_LIMITS[p]:,}")

    if st.button("🚀 Generate with AI", use_container_width=True):
        if not api_key:
            st.error("Enter your Anthropic API key above.")
        elif not ai_prompt.strip():
            st.error("Enter a topic or brief first.")
        elif not selected:
            st.error("Select at least one platform.")
        else:
            platforms_str = ", ".join(selected)
            min_lim = min(PLATFORM_LIMITS[p] for p in selected)
            system_prompt = (
                f"You are a social media expert. Generate {ai_count} distinct social media posts "
                f"based on the user's brief. Target platforms: {platforms_str}. "
                f"Keep each message under {min_lim} characters (the tightest platform limit). "
                f"Return ONLY a JSON array, no markdown, no extra text. "
                f'Each item: {{"message": "...", "category": "", "hashtagGroup": ""}}'
            )
            with st.spinner(f"Generating {ai_count} posts..."):
                try:
                    client = anthropic.Anthropic(api_key=api_key)
                    response = client.messages.create(
                        model="claude-opus-4-5",
                        max_tokens=1500,
                        system=system_prompt,
                        messages=[{"role": "user", "content": ai_prompt}]
                    )
                    raw = response.content[0].text.strip()
                    raw = raw.replace("```json", "").replace("```", "").strip()
                    parsed = json.loads(raw)
                    new_posts = []
                    for item in parsed:
                        p = empty_post()
                        p["Message"] = item.get("message", "")
                        p["Category"] = item.get("category", "")
                        p["HashtagGroup"] = item.get("hashtagGroup", "")
                        p["_ai"] = True
                        new_posts.append(p)
                    st.session_state.posts.extend(new_posts)
                    st.success(f"✅ Generated {len(new_posts)} posts!")
                    st.rerun()
                except json.JSONDecodeError:
                    st.error("Could not parse AI response. Try again.")
                except Exception as e:
                    st.error(f"API error: {e}")

    st.divider()

    # ── Quick defaults ───────────────────────────────────────────────────────
    st.markdown("### ⚡ Quick Fill")
    default_wm = st.text_input("Default watermark", placeholder="Default")
    default_htg = st.text_input("Default hashtag group", placeholder="e.g. SummerSale")
    if st.button("Apply to all rows", use_container_width=True):
        for p in st.session_state.posts:
            if default_wm:
                p["Watermark"] = default_wm
            if default_htg:
                p["HashtagGroup"] = default_htg
        st.success("Applied!")
        st.rerun()

    st.divider()

    # ── CSV Actions ──────────────────────────────────────────────────────────
    st.markdown("### 📁 CSV Actions")
    st.download_button(
        "⬇️ Download template CSV",
        data=get_template_bytes(),
        file_name="bulk_posts_template.csv",
        mime="text/csv",
        use_container_width=True
    )
    uploaded = st.file_uploader("⬆️ Import CSV", type=["csv"])
    if uploaded:
        try:
            df = pd.read_csv(uploaded, dtype=str).fillna("")
            imported = df_to_posts(df)
            st.session_state.posts.extend(imported)
            st.success(f"Imported {len(imported)} rows!")
            st.rerun()
        except Exception as e:
            st.error(f"Import error: {e}")

    if st.session_state.posts:
        st.download_button(
            "⬆️ Export CSV",
            data=get_csv_bytes(),
            file_name=f"bulk_posts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )

# ── MAIN AREA ─────────────────────────────────────────────────────────────────
st.title("📢 Bulk Post Creator")
st.caption("Create, edit, schedule, and export social media posts in bulk.")

# ── Stats bar ────────────────────────────────────────────────────────────────
posts = st.session_state.posts
total = len(posts)
scheduled = sum(1 for p in posts if get_status(p) == "scheduled")
queued = sum(1 for p in posts if get_status(p) == "queued")
with_media = sum(1 for p in posts if p.get("ImageURL") or p.get("VideoURL"))
ai_count_stat = sum(1 for p in posts if p.get("_ai"))

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total posts", total)
c2.metric("Scheduled", scheduled)
c3.metric("Queued", queued)
c4.metric("With media", with_media)
c5.metric("AI-generated", ai_count_stat)

st.divider()

# ── Action buttons ────────────────────────────────────────────────────────────
col_add, col_clear, col_space = st.columns([1, 1, 6])
if col_add.button("➕ Add empty post"):
    st.session_state.posts.append(empty_post())
    st.session_state.edit_idx = len(st.session_state.posts) - 1
    st.rerun()
if col_clear.button("🗑️ Clear all", type="secondary"):
    st.session_state.posts = []
    st.session_state.edit_idx = None
    st.rerun()

st.divider()

# ── Edit panel (shown when editing) ──────────────────────────────────────────
if st.session_state.edit_idx is not None:
    idx = st.session_state.edit_idx
    if 0 <= idx < len(st.session_state.posts):
        p = st.session_state.posts[idx]
        with st.expander(f"✏️ Editing post #{idx + 1}", expanded=True):
            st.markdown("#### ✏️ Edit Post")

            msg = st.text_area("Message *", value=p.get("Message", ""), height=120, key=f"edit_msg_{idx}")
            if msg and st.session_state.selected_platforms:
                char_count = len(msg)
                min_lim = min(PLATFORM_LIMITS[pl] for pl in st.session_state.selected_platforms)
                color = "🔴" if char_count > min_lim else "🟢"
                st.caption(f"{color} {char_count:,} / {min_lim:,} chars (tightest: {min(st.session_state.selected_platforms, key=lambda x: PLATFORM_LIMITS[x])})")

            ec1, ec2 = st.columns(2)
            link = ec1.text_input("Link URL", value=p.get("Link", ""), key=f"edit_link_{idx}")
            pin_title = ec2.text_input("Pin title (Pinterest)", value=p.get("PinTitle", ""), key=f"edit_pin_{idx}")

            img_url = st.text_input("Image URL(s) — separate multiple with comma, no spaces", value=p.get("ImageURL", ""), key=f"edit_img_{idx}")
            vid_url = st.text_input("Video URL (.mp4 only)", value=p.get("VideoURL", ""), key=f"edit_vid_{idx}")
            if img_url and vid_url:
                st.warning("⚠️ Don't fill both ImageURL and VideoURL — upload will fail.")

            ec3, ec4 = st.columns(2)
            category = ec3.text_input("Category", value=p.get("Category", ""), key=f"edit_cat_{idx}")
            watermark = ec4.text_input("Watermark", value=p.get("Watermark", ""), placeholder="Default", key=f"edit_wm_{idx}")

            ec5, ec6 = st.columns(2)
            hashtag = ec5.text_input("Hashtag group", value=p.get("HashtagGroup", ""), key=f"edit_htg_{idx}")
            cta = ec6.text_input("CTA group", value=p.get("CTAGroup", ""), key=f"edit_cta_{idx}")

            first_comment = st.text_area("First comment (FB, IG, LinkedIn, Bluesky, Threads)", value=p.get("FirstComment", ""), height=70, key=f"edit_fc_{idx}")

            ec7, ec8 = st.columns(2)
            story = ec7.text_input("Story (Y or N)", value=p.get("Story(YorN)", ""), key=f"edit_story_{idx}")
            pinterest_board = ec8.text_input("Pinterest board", value=p.get("PinterestBoard", ""), key=f"edit_pb_{idx}")

            ec9, ec10 = st.columns(2)
            alt_text = ec9.text_input("Alt text", value=p.get("AltText", ""), key=f"edit_alt_{idx}")
            post_preset = ec10.text_input("Post preset", value=p.get("PostPreset", ""), key=f"edit_preset_{idx}")
            vid_thumb = st.text_input("Video thumbnail URL", value=p.get("VideoThumbnailURL", ""), key=f"edit_vt_{idx}")

            st.markdown("**⏰ Schedule (leave blank to queue)**")
            sc1, sc2, sc3, sc4, sc5 = st.columns(5)
            month = sc1.text_input("Month (1-12)", value=p.get("Month(1-12)", ""), key=f"edit_mo_{idx}")
            day = sc2.text_input("Day (1-31)", value=p.get("Day(1-31)", ""), key=f"edit_day_{idx}")
            year = sc3.text_input("Year", value=p.get("Year", ""), placeholder="2025", key=f"edit_yr_{idx}")
            hour = sc4.text_input("Hour (0-23)", value=p.get("Hour", ""), key=f"edit_hr_{idx}")
            minute = sc5.text_input("Minute / Random", value=p.get("Minute(0-59)", ""), placeholder="0", key=f"edit_min_{idx}")

            sb1, sb2 = st.columns([1, 5])
            if sb1.button("💾 Save post", type="primary"):
                st.session_state.posts[idx].update({
                    "Message": msg, "Link": link, "ImageURL": img_url, "VideoURL": vid_url,
                    "Month(1-12)": month, "Day(1-31)": day, "Year": year, "Hour": hour, "Minute(0-59)": minute,
                    "PinTitle": pin_title, "Category": category, "Watermark": watermark,
                    "HashtagGroup": hashtag, "VideoThumbnailURL": vid_thumb, "CTAGroup": cta,
                    "FirstComment": first_comment, "Story(YorN)": story, "PinterestBoard": pinterest_board,
                    "AltText": alt_text, "PostPreset": post_preset, "_ai": False
                })
                st.session_state.edit_idx = None
                st.success("Post saved!")
                st.rerun()
            if sb2.button("✖ Cancel"):
                st.session_state.edit_idx = None
                st.rerun()

    st.divider()

# ── Posts table ───────────────────────────────────────────────────────────────
if not st.session_state.posts:
    st.info("No posts yet. Add posts manually or use the AI generator in the sidebar.")
else:
    st.markdown(f"### Posts ({len(st.session_state.posts)})")

    # Column headers
    h0, h1, h2, h3, h4, h5, h6, h7 = st.columns([0.4, 3, 2, 1.2, 1.2, 1.5, 1, 1.2])
    h0.markdown("**#**")
    h1.markdown("**Message**")
    h2.markdown("**Link**")
    h3.markdown("**Image**")
    h4.markdown("**Video**")
    h5.markdown("**Schedule**")
    h6.markdown("**Status**")
    h7.markdown("**Actions**")
    st.markdown("---")

    to_delete = None

    for i, post in enumerate(st.session_state.posts):
        msg = post.get("Message", "")
        link = post.get("Link", "")
        img = post.get("ImageURL", "")
        vid = post.get("VideoURL", "")
        mo = post.get("Month(1-12)", "")
        da = post.get("Day(1-31)", "")
        yr = post.get("Year", "")
        hr = post.get("Hour", "")
        mn = post.get("Minute(0-59)", "") or "00"
        status = get_status(post)
        is_ai = post.get("_ai", False)

        schedule_str = f"{yr}-{str(mo).zfill(2)}-{str(da).zfill(2)} {hr}:{mn}" if all([mo, da, yr, hr]) else "Queue"
        msg_preview = (msg[:60] + "…") if len(msg) > 60 else msg or "_empty_"

        c0, c1, c2, c3, c4, c5, c6, c7 = st.columns([0.4, 3, 2, 1.2, 1.2, 1.5, 1, 1.2])
        c0.markdown(f"**{i+1}**")

        ai_badge = " 🤖" if is_ai else ""
        c1.markdown(f"{msg_preview}{ai_badge}")

        link_disp = (link[:30] + "…") if len(link) > 30 else link
        c2.caption(link_disp or "—")

        if img:
            c3.markdown("✅ Image")
        else:
            c3.caption("—")

        if vid:
            c4.markdown("✅ Video")
        else:
            c4.caption("—")

        c5.caption(schedule_str)

        status_icons = {"scheduled": "🔵 Scheduled", "queued": "🟢 Queued", "empty": "🔴 Empty"}
        c6.markdown(status_icons[status])

        act1, act2 = c7.columns(2)
        if act1.button("✏️", key=f"edit_{i}", help="Edit post"):
            st.session_state.edit_idx = i
            st.rerun()
        if act2.button("🗑", key=f"del_{i}", help="Delete post"):
            to_delete = i

        if i < len(st.session_state.posts) - 1:
            st.markdown("<hr style='margin:4px 0; border-color:#f0f0f0'>", unsafe_allow_html=True)

    if to_delete is not None:
        st.session_state.posts.pop(to_delete)
        if st.session_state.edit_idx == to_delete:
            st.session_state.edit_idx = None
        st.rerun()

    st.divider()

    # ── Preview as DataFrame ─────────────────────────────────────────────────
    with st.expander("📊 Preview as spreadsheet"):
        df = posts_to_df()
        st.dataframe(df, use_container_width=True, height=300)

    # ── Inline bulk edit ─────────────────────────────────────────────────────
    with st.expander("✏️ Bulk edit as spreadsheet"):
        st.caption("Edit cells directly. Press Apply to save changes.")
        df = posts_to_df()
        edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic", height=300)
        if st.button("✅ Apply spreadsheet changes"):
            existing_ais = [p.get("_ai", False) for p in st.session_state.posts]
            new_posts = df_to_posts(edited_df)
            for i, p in enumerate(new_posts):
                p["_ai"] = existing_ais[i] if i < len(existing_ais) else False
            st.session_state.posts = new_posts
            st.success("Changes saved!")
            st.rerun()

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("💡 Tip: Use the AI generator to draft posts, then edit and schedule them. Export when ready.")
