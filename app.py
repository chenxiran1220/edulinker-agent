import streamlit as st
import pandas as pd
import requests
import re
import time
import urllib.parse

# 设置网页信息
st.set_page_config(page_title="EduLinker", page_icon="🎓", layout="wide")

# ==========================================
# 核心搜索代码（一字未改，保留高准确率！）
# ==========================================
def search_scholar_email(name, institution, api_key):
    url = "https://google.serper.dev/search"
    query = f"{name} {institution} email"
    payload = {"q": query}
    headers = {
        'X-API-KEY': api_key,
        'Content-Type': 'application/json'
    }
    try:
        response = requests.post(url, headers=headers, json=payload)
        result = response.json()
        snippets = ""
        if "organic" in result:
            for item in result["organic"]:
                snippets += item.get("snippet", "") + " "
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', snippets)
        if emails:
            return list(set(emails))[0], "🟢 已找到"
        return "未找到", "🔴 需人工核查"
    except Exception as e:
        return f"错误: {str(e)}", "⚠️ 接口异常"

# ==========================================
# 状态初始化
# ==========================================
if 'api_key' not in st.session_state:
    st.session_state.api_key = ""
if 'search_results' not in st.session_state:
    st.session_state.search_results = None

# ==========================================
# 顶部：极简标题 & 隐藏式后台设置
# ==========================================
col_title, col_settings = st.columns([8, 2])
with col_title:
    # 优化1：极简名称与一句话介绍
    st.title("🎓 EduLinker")
    st.markdown("面向学术编辑部的自动化联络 Agent，从精准寻址到一键邀约。")

with col_settings:
    st.write("") 
    # 优化1：后台设置依然保留在右上角
    with st.popover("⚙️ 后台设置"):
        st.markdown("**系统配置**")
        temp_key = st.text_input("Serper API Key", value=st.session_state.api_key, type="password")
        if st.button("保存设置"):
            st.session_state.api_key = temp_key
            st.success("密钥已保存！")

st.divider()

# ==========================================
# 优化4：使用 Tabs 实现“索引贴”分隔页效果
# ==========================================
tab1, tab2 = st.tabs(["📑 第一层：自动寻址工作台", "📧 第二层：邮件撰写工作台"])

# ==========================================
# 第一层：数据准备与寻址
# ==========================================
with tab1:
    # 优化2：从上至下的瀑布流排版，占满整个页面
    uploaded_file = st.file_uploader("📁 请上传包含学者名单的 CSV 文件", type=['csv'])
    
    # 优化2：将下载模板放在下方，做成小巧的辅助按钮
    template_df = pd.DataFrame({"authfull": ["Robert Sternberg"], "inst_name": ["Cornell University"], "title": ["Professor"], "status": ["Active"]})
    csv_template = template_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(label="📥 找不到格式？点击下载 CSV 空白模板", data=csv_template, file_name="EduLinker_模板.csv", mime="text/csv")

    st.write("") # 增加一点呼吸空间

    if uploaded_file is not None:
        input_df = pd.read_csv(uploaded_file)
        
        if st.button("🚀 开始智能检索", type="primary"):
            if not st.session_state.api_key:
                st.error("请先在右上角【⚙️ 后台设置】中填写 API Key！")
            else:
                results = []
                progress_bar = st.progress(0)
                status_text = st.empty()
                total = len(input_df)
                
                for index, row in input_df.iterrows():
                    name = row.get('authfull', '未知')
                    inst = row.get('inst_name', '未知')
                    # 尝试读取职位和状态，如果没有则填入默认值
                    title = row.get('title', 'Professor/Researcher')
                    status_val = row.get('status', '2026 活跃')
                    
                    status_text.text(f"正在检索 ({index+1}/{total}): {name}")
                    email, search_status = search_scholar_email(name, inst, st.session_state.api_key)
                    
                    # 优化3：结果展示增加职位和学者状态
                    results.append({
                        "学者姓名": name, 
                        "所属机构": inst, 
                        "职位": title,
                        "学者状态": status_val,
                        "提取邮箱": email, 
                        "状态": search_status
                    })
                    
                    progress_bar.progress((index + 1) / total)
                    time.sleep(0.1)
                    
                status_text.text("✅ 寻址完成！结果已生成，可切换至上方【第二层】进行邮件撰写。")
                st.session_state.search_results = pd.DataFrame(results)
                
        # 展示检索结果表格
        if st.session_state.search_results is not None:
            st.subheader("📊 检索结果概览")
            st.dataframe(st.session_state.search_results, use_container_width=True)
            
            final_csv = st.session_state.search_results.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 下载完整结果报告", data=final_csv, file_name="EduLinker_检索结果.csv")

# ==========================================
# 第二层：撰写与发送
# ==========================================
with tab2:
    if st.session_state.search_results is None:
        st.info("👈 请先在【第一层】完成学者名单的上传与自动寻址。")
    else:
        st.markdown("### 智能邮件工作台")
        st.caption("已为您过滤出成功找到邮箱的学者。系统已为您自动生成初步的联络草稿，您可以审核并一键发送。")
        
        df_results = st.session_state.search_results
        success_df = df_results[df_results['提取邮箱'] != '未找到']
        
        if success_df.empty:
            st.warning("本次检索未能找到有效邮箱。")
        else:
            for index, row in success_df.iterrows():
                name = row['学者姓名']
                email = row['提取邮箱']
                inst = row['所属机构']
                
                with st.expander(f"👤 {name} - {inst} ({email})", expanded=False):
                    default_subject = f"Invitation to Contribute to ROE Journal - {name}"
                    default_body = f"Dear {name},\n\nWe hope this email finds you well at {inst}.\n\nGiven your distinguished research in the field of education, the editorial board of Research on Education (ROE) would be honored to invite you to contribute an article to our upcoming special issue.\n\nWe look forward to hearing from you.\n\nBest regards,\n\nROE Editorial Board"
                    
                    edited_subject = st.text_input("邮件主题", value=default_subject, key=f"sub_{index}")
                    edited_body = st.text_area("邮件正文 (AI 预生成)", value=default_body, height=150, key=f"body_{index}")
                    
                    # 生成跳转链接
                    safe_subject = urllib.parse.quote(edited_subject)
                    safe_body = urllib.parse.quote(edited_body)
                    mailto_link = f"mailto:{email}?subject={safe_subject}&body={safe_body}"
                    
                    col_copy, col_send = st.columns([8, 2])
                    with col_copy:
                        st.code(edited_body, language="markdown")
                        st.caption("↑ 鼠标悬浮在代码框右上角即可一键复制纯文本。")
                    with col_send:
                        st.markdown("<br><br>", unsafe_allow_html=True) # 稍微往下沉一点对齐
                        st.markdown(f'<a href="{mailto_link}" target="_blank"><button style="background-color:#4CAF50; color:white; padding:10px 20px; border:none; border-radius:5px; cursor:pointer; width:100%;">📧 唤起邮箱发送</button></a>', unsafe_allow_html=True)