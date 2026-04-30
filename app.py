import streamlit as st
import pandas as pd
import requests
import re
import time
import urllib.parse
import json

# --- 🌟 新增的拼音库引入逻辑，紧跟在原有的 import 后面 ---
try:
    from pypinyin import pinyin, Style
    HAS_PINYIN = True
except ImportError:
    HAS_PINYIN = False

# 设置网页信息
st.set_page_config(page_title="EduLinker", page_icon="🎓", layout="wide")

# ----------------- 核心逻辑：强制初始化所有状态变量 -----------------
# 1. 初始化搜索结果（这是解决你 AttributeError 的关键）
if 'search_results' not in st.session_state:
    st.session_state.search_results = None

# 2. 从 Secrets 或内置机密中读取配置
if 'api_key' not in st.session_state:
    st.session_state.api_key = st.secrets.get("SERPER_API_KEY", "")

if 'db_url' not in st.session_state:
    st.session_state.db_url = st.secrets.get("DATABASE_URL", "")

# 3. 初始化用户信息
if 'real_name' not in st.session_state:
    st.session_state.real_name = st.secrets.get("DEFAULT_REAL_NAME", "演示账号")

if 'dept_name' not in st.session_state:
    st.session_state.dept_name = st.secrets.get("DEFAULT_DEPT_NAME", "Review Of Education")

# 4. 合成用户完整显示名
if 'user_name' not in st.session_state:
    st.session_state.user_name = f"{st.session_state.real_name} - {st.session_state.dept_name}"

# ------------------------------------------------------------------
#核心邮箱查询代码
# ------------------------------------------------------------------
def search_scholar_email(name, institution, api_key):
    url = "https://google.serper.dev/search"
    
    is_chinese = bool(re.search(r'[\u4e00-\u9fa5]', name))
    
    # 🌟 改进 1：搜索词里直接“点名”QQ 和 163 邮箱，强制 Google 抓取它们
    if is_chinese:
        query_str = f"{name} {institution} (邮箱 OR email OR qq.com OR 163.com OR 师资队伍)"
    else:
        query_str = f'"{name}" {institution} (email OR "CV" OR profile)'
        
    query = urllib.parse.quote(query_str)
    headers = {'X-API-KEY': api_key}
    
    # 排除常见的机构邮箱词汇
    blacklist = ['support', 'info', 'admin', 'service', 'contact', 'office', 'hr', 'library', 'dean', 
                 'admission', 'ceit', 'department', 'school', 'public', 'official', 'enquiry', 'webmaster']
    
    try:
        response = requests.get(url + f"?q={query}", headers=headers, timeout=15)
        result = response.json()
        
        if "organic" in result:
            email_candidates = {} 
            
            # 提取姓名拼音特征
            name_parts = []
            initials = ""
            if is_chinese and HAS_PINYIN:
                name_parts = [p[0].lower() for p in pinyin(name, style=Style.NORMAL)]
                initials = "".join([p[0] for p in name_parts]) 
            else:
                name_parts = re.findall(r'[a-z]+', name.lower())
                initials = "".join([p[0] for p in name_parts if p])

            for item in result["organic"][:8]: # 扩大搜索范围到前 8 条结果
                snippet = item.get("snippet", "").lower()
                link = item.get("link", "").lower()
                found_emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', snippet)
                
                for email in found_emails:
                    if email not in email_candidates:
                        email_candidates[email] = {"score": 0, "link": item.get("link", "")}
            
            if not email_candidates:
                return "未找到", "🔴 未发现任何邮箱", "无来源"
            
            for email, data in email_candidates.items():
                prefix = email.split('@')[0]
                domain = email.split('@')[1]
                link_lower = data["link"].lower()
                score = 0
                
                # --- 评分逻辑开始 ---
                
                # 🌟 改进 2：姓名拼音权重（解决 zhangscnu 问题）
                # 只要邮箱前缀包含姓氏全拼或首字母缩写
                if any(part in prefix for part in name_parts if len(part) > 1):
                    score += 60 
                elif initials in prefix and len(initials) >= 2:
                    score += 45
                
                # 🌟 改进 3：处理“全数字 QQ 邮箱”
                # 如果是纯数字前缀且在师资页面，给一个基础信任分
                if prefix.isdigit() and "qq.com" in domain:
                    if any(kw in link_lower for kw in ['szdw', 'teacher', 'faculty', 'people']):
                        score += 50 # 老师主页上的数字 QQ 邮箱通常是真实的
                
                # 域名分
                if '.edu' in domain: score += 15
                if is_chinese and ("163.com" in domain or "qq.com" in domain):
                    score += 10
                
                # 来源加成：师资网/主页链接
                if any(kw in link_lower for kw in ['szdw', 'teacher', 'faculty', 'people', 'profile']):
                    score += 25
                
                # 黑名单严厉惩罚
                if any(b in prefix for b in blacklist):
                    score -= 150 
                
                email_candidates[email]["score"] = score
            
            # 决选
            best_email = max(email_candidates, key=lambda x: email_candidates[x]["score"])
            best_data = email_candidates[best_email]
            
            if best_data["score"] >= 40: # 降低一点门槛，确保数字 QQ 也能通过
                return best_email, f"🟢 匹配成功 (得分: {best_data['score']})", best_data["link"]
            elif best_data["score"] >= 10:
                return best_email, "🟡 疑似个人邮箱", best_data["link"]
            else:
                return "未找到", "🔴 仅识别到公共/机构邮箱", "无来源"

        return "未找到", "🔴 需人工核查", "无来源"
    except Exception as e:
        return "错误", "⚠️ 接口异常", "无来源"

# ==========================================
# 云端读写函数
# ==========================================
def save_to_custom_db(url, data_dict):
    try:
        requests.post(url, data=json.dumps(data_dict), timeout=10)
    except:
        pass

def load_from_custom_db(url):
    try:
        response = requests.get(url, timeout=15)
        if "<html" in response.text.lower(): return "AUTH_ERROR"
        raw_data = response.json()
        if len(raw_data) > 1:
            return pd.DataFrame(raw_data[1:], columns=raw_data[0])
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# ==========================================
# 重新补回：云端数据库读写函数
# ==========================================
def save_to_custom_db(url, data_dict):
    """将搜索到的学者信息同步到 Google 表格或自定义数据库"""
    try:
        # 使用 json.dumps 确保数据格式正确
        requests.post(url, data=json.dumps(data_dict), timeout=10)
    except:
        pass

def load_from_custom_db(url):
    """从云端资产库加载已有的学者数据"""
    try:
        response = requests.get(url, timeout=15)
        # 防错机制：如果返回的是网页 HTML 而非 JSON，说明 URL 填错了或权限失效
        if "<html" in response.text.lower(): return "AUTH_ERROR"
        
        raw_data = response.json()
        if len(raw_data) > 1:
            # 将第一行作为表头，其余作为内容转换为 DataFrame[cite: 1]
            return pd.DataFrame(raw_data[1:], columns=raw_data[0])
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# ==========================================
# UI 布局
# ==========================================
st.markdown("""
    <style>
    .simple-title { font-size: 3rem; font-weight: bold; color: #1e3a8a; margin-bottom: 0px;}
    .simple-subtitle { font-size: 1.2rem; color: #6b7280; margin-top: 0px; margin-bottom: 30px;}
    </style>
    """, unsafe_allow_html=True)

col_title, col_set = st.columns([7, 3])
with col_title:
    st.markdown('<div class="simple-title">EduLinker</div>', unsafe_allow_html=True)
    st.markdown('<div class="simple-subtitle">Make academic exchange easier</div>', unsafe_allow_html=True)

with col_set:
    # 检查是否已经成功加载内置配置
    is_ready = st.session_state.api_key and st.session_state.db_url
    
    with st.popover("⚙️ 配置中心 (已预设)" if is_ready else "⚠️ 必填配置"):
        st.session_state.real_name = st.text_input("👤 姓名", value=st.session_state.real_name)
        st.session_state.dept_name = st.text_input("🏢 编辑部全称", value=st.session_state.dept_name)
        st.session_state.db_url = st.text_input("🔗 专属数据库 URL", value=st.session_state.db_url)
        st.session_state.api_key = st.text_input("🔑 Serper API KEY", value=st.session_state.api_key, type="password")
        
        if st.button("💾 更新配置"):
            st.success("配置已手动更新！")

    # 🌟 评委一眼就能看到的绿灯提示
    if is_ready:
        st.markdown(f"✅ **系统已就绪** (欢迎您，{st.session_state.real_name})")
    else:
        st.error("❌ 配置缺失，请展开上方手动填写")
tab1, tab2, tab3 = st.tabs(["📑 第一层：自动寻址", "📧 第二层：邮件撰写", "🏛️ 第三层：编辑部资产库"])


# ----------------- 第一层：自动寻址 (双模式引擎版) -----------------
with tab1:
    # 🌟 新增：模式切换开关
    search_mode = st.radio("🔍 请选择工作模式", ["批量名单检索 (CSV上传)", "单人极速寻址 (手动输入)"], horizontal=True)
    st.markdown("---")

    # ==========================================
    # 模式一：批量名单检索 (你之前已经完美跑通的代码)
    # ==========================================
    if search_mode == "批量名单检索 (CSV上传)":
        template_df = pd.DataFrame({
            "authfull": ["Robert Sternberg", "John Dewey"], 
            "inst_name": ["Cornell University", "Columbia University"], 
            "title": ["Professor", "Researcher"], 
            "status": ["Active", "Active"]
        })
        st.download_button("📥 下载 CSV 空白名单模板", data=template_df.to_csv(index=False).encode('utf-8-sig'), file_name="EduLinker_Upload_Template.csv", mime="text/csv")
        st.info("💡 **填表说明**：上传的 CSV 中请包含 **'authfull' (学者姓名)** 和 **'inst_name' (工作单位)**。")

        uploaded_file = st.file_uploader("📁 请上传包含学者名单的 CSV 文件", type=['csv'])
        
        if uploaded_file and st.button("🚀 开始批量检索并同步云端"):
            if not st.session_state.api_key or not st.session_state.db_url:
                st.error("请先在右上角【必填配置】中填写 API Key 和 数据库 URL！")
            else:
                input_df = pd.read_csv(uploaded_file)
                results = []
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                total_scholars = len(input_df)
                
                with st.spinner("正在比对云端资产库，为您节省 API 额度..."):
                    db_df = load_from_custom_db(st.session_state.db_url)
                    name_col_db, email_col_db, source_col_db = None, None, None
                    
                    if not isinstance(db_df, str) and not db_df.empty:
                        db_df.columns = [str(c).strip() for c in db_df.columns]
                        all_cols = db_df.columns.tolist()
                        name_col_db = next((c for c in all_cols if "姓名" in c or "Name" in c), None)
                        email_col_db = next((c for c in all_cols if "邮箱" in c or "email" in c.lower()), None)
                        source_col_db = next((c for c in all_cols if "来源" in c or "source" in c.lower()), None)
                    else:
                        db_df = pd.DataFrame()

                for idx, row in input_df.iterrows():
                    name, inst = row.get('authfull','未知'), row.get('inst_name','未知')
                    status_text.text(f"正在检索 ({idx + 1}/{total_scholars}): {name}")
                    
                    email, status, source_url, need_api_call = "未找到", "🔴 需人工核查", "无来源", True 
                    
                    if not db_df.empty and name_col_db and email_col_db:
                        match = db_df[(db_df[name_col_db] == name) & (db_df[email_col_db] != '未找到') & (db_df[email_col_db].notna())]
                        if not match.empty:
                            email, status = str(match.iloc[-1][email_col_db]), "🔵 数据库调取"
                            source_url = str(match.iloc[-1].get(source_col_db, '历史数据')) if source_col_db else '历史数据'
                            need_api_call = False
                    
                    if need_api_call:
                        email, status, source_url = search_scholar_email(name, inst, st.session_state.api_key)
                        if email != "未找到":
                            save_to_custom_db(st.session_state.db_url, {
                                "name": name, "institution": inst, "title": row.get('title','Researcher'), 
                                "status_val": row.get('status','Active'), "email": email, "status": status,
                                "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                                "owner": st.session_state.user_name, "source_url": source_url
                            })
                    
                    results.append({"学者姓名": name, "所属机构": inst, "提取邮箱": email, "状态": status, "网页来源": source_url})
                    progress_bar.progress((idx + 1) / total_scholars)
                
                status_text.text("✅ 批量寻址完成，新数据已同步至云端！")
                st.session_state.search_results = pd.DataFrame(results)
                
        if st.session_state.search_results is not None:
            st.dataframe(st.session_state.search_results, use_container_width=True)
            csv_data = st.session_state.search_results.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 下载本次搜索结果表格", data=csv_data, file_name="EduLinker_Batch_Result.csv", mime="text/csv")


    # ==========================================
    # 模式二：单人极速寻址 (新增功能)
    # ==========================================
    elif search_mode == "单人极速寻址 (手动输入)":
        st.markdown("### ⚡ 单人极速查询工作台")
        col_s1, col_s2 = st.columns(2)
        
        with col_s1:
            single_name = st.text_input("👤 学者姓名", placeholder="例如：Paulo Freire")
        with col_s2:
            single_inst = st.text_input("🏫 所属机构 / 工作单位", placeholder="例如：Harvard University")
            
        if st.button("🔍 立即检索此人", use_container_width=True):
            if not st.session_state.api_key or not st.session_state.db_url:
                st.error("请先在右上角【必填配置】中填写 API Key 和 数据库 URL！")
            elif not single_name or not single_inst:
                st.warning("⚠️ 请完整输入学者的姓名和机构！")
            else:
                with st.spinner(f"正在全网扫描 {single_name} 的联系方式..."):
                    # 1. 拦截器：先查库
                    db_df = load_from_custom_db(st.session_state.db_url)
                    name_col_db, email_col_db, source_col_db = None, None, None
                    
                    if not isinstance(db_df, str) and not db_df.empty:
                        db_df.columns = [str(c).strip() for c in db_df.columns]
                        all_cols = db_df.columns.tolist()
                        name_col_db = next((c for c in all_cols if "姓名" in c or "Name" in c), None)
                        email_col_db = next((c for c in all_cols if "邮箱" in c or "email" in c.lower()), None)
                        source_col_db = next((c for c in all_cols if "来源" in c or "source" in c.lower()), None)
                    else:
                        db_df = pd.DataFrame()

                    email, status, source_url, need_api_call = "未找到", "🔴 需人工核查", "无来源", True
                    
                    if not db_df.empty and name_col_db and email_col_db:
                        match = db_df[(db_df[name_col_db] == single_name) & (db_df[email_col_db] != '未找到') & (db_df[email_col_db].notna())]
                        if not match.empty:
                            email, status = str(match.iloc[-1][email_col_db]), "🔵 数据库调取"
                            source_url = str(match.iloc[-1].get(source_col_db, '历史数据')) if source_col_db else '历史数据'
                            need_api_call = False
                            st.toast('从云端资产库中秒传成功！', icon='⚡')

                    # 2. 如果库里没有，查 API 并写入库
                    if need_api_call:
                        email, status, source_url = search_scholar_email(single_name, single_inst, st.session_state.api_key)
                        if email != "未找到":
                            save_to_custom_db(st.session_state.db_url, {
                                "name": single_name, "institution": single_inst, "title": "Researcher", 
                                "status_val": "Active", "email": email, "status": status,
                                "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                                "owner": st.session_state.user_name, "source_url": source_url
                            })

                    # ==========================================
                    # 3. 优雅地展示单人结果卡片并展开撰写平台 (你的核心需求)
                    # ==========================================
                    st.markdown("---")
                    if email != "未找到":
                        # 3.1 展示结果卡片
                        st.success(f"🎉 **成功获取联系方式！** ({status})")
                        st.info(f"📧 **提取邮箱**: `{email}`\n\n🔗 **溯源核查**: [点击访问网页来源]({source_url})")
                        
                        # 3.2 无缝衔接的“极速撰写平台”
                        st.markdown("### ✍️ 专属邮件撰写台")
                        
                        # 智能提取姓氏用于预填 (处理 "Ball, Stephen" 或 "Stephen Ball")
                        clean_n = single_name.replace(',', ' ')
                        last_name_guess = single_name.split(',')[0].strip() if ',' in single_name else clean_n.split()[-1]
                        
                        # 提供学术邮件默认模板
                        default_subject = f"Inquiry regarding your research at {single_inst}"
                        default_body = (
                            f"Dear Prof. {last_name_guess},\n\n"
                            f"I hope this email finds you well. I have been following your excellent work at {single_inst}.\n\n"
                            f"[此处填写您对教授研究的具体见解或提问]\n\n"
                            f"Best regards,\n"
                            f"Xiran Chen\n"
                            f"Education Major, South China Normal University"
                        )
                        
                        # 渲染输入框，允许用户在网页里修改
                        email_subject = st.text_input("🏷️ 邮件主题", value=default_subject)
                        email_body = st.text_area("📄 邮件正文", value=default_body, height=250)
                        
                        # 生成 HTML 一键发送按钮
                        import urllib.parse
                        safe_subject = urllib.parse.quote(email_subject)
                        safe_body = urllib.parse.quote(email_body)
                        mailto_link = f"mailto:{email}?subject={safe_subject}&body={safe_body}"
                        
                        st.markdown(
                            f'''
                            <a href="{mailto_link}" target="_blank">
                                <button style="background-color:#4CAF50; color:white; padding:10px 24px; border:none; border-radius:6px; cursor:pointer; font-size: 16px; font-weight: bold; width: 100%;">
                                    🚀 确认无误，一键唤起本地邮箱发送
                                </button>
                            </a>
                            ''', 
                            unsafe_allow_html=True
                        )
                    else:
                        st.error("⚠️ 未能提取到有效邮箱，建议点击下方链接人工核查。")
                        
                        # 这里修复一个小细节：如果没找到，自动生成一个去 Google 搜索的链接
                        fallback_url = f"https://www.google.com/search?q={urllib.parse.quote(single_name + ' ' + single_inst + ' email')}"
                        st.info(f"🔗 **溯源核查**: [去 Google 查看]({fallback_url})")

# ----------------- 第二层：邮件撰写 (逻辑完全咬合版) -----------------
with tab2:
    # --- 展示并提供下载当前搜索结果 (安全增强版) ---
    if st.session_state.get('search_results') is not None:
        df_results = st.session_state.search_results
        
        # 🌟 这里的 if 确保了表格不是空的才进行筛选
        if not df_results.empty:
            # 只有表格里有数据，才执行这一行，彻底解决 TypeError
            success_df = df_results[df_results['提取邮箱'] != '未找到']
            
            st.dataframe(df_results, use_container_width=True)
            
            # 展示一个小统计
            st.success(f"🎊 本次检索完成！共发现 {len(success_df)} 个有效邮箱。")
            
            csv_data = df_results.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 下载本次搜索结果表格", data=csv_data, file_name="EduLinker_Result.csv", mime="text/csv")
        else:
            st.warning("⚠️ 暂无搜索结果，请上传文件或输入姓名开始检索。")
        
        if success_df.empty:
            st.warning("本次搜索未能提取到有效邮箱，无法生成邮件。")
        else:
            # 1. 核心数据库：初始化/保存系统模板
            if 'email_templates' not in st.session_state:
                st.session_state.email_templates = {
                    "特刊约稿": "Dear {name},\n\nWe are writing to cordially invite you to contribute to our upcoming Special Issue in Review of Education. Given your extensive expertise in this field, your insights would be invaluable to our readers.\n\nPlease let us know if you would be interested in submitting a manuscript.\n\nLooking forward to your positive response.{signature}",
                    
                    "审稿邀请": "Dear {name},\n\nReview of Education has recently received a manuscript that aligns closely with your research interests. We would be honored if you could serve as a peer reviewer for this paper.\n\nYour expert feedback ensures the high academic standard of our publication.\n\nThank you for your time and contribution to the academic community.{signature}",
                    
                    "日常推文": "Dear {name},\n\nWe are excited to share the latest published articles and academic news from Review of Education. We hope you find these updates insightful for your own educational research.{signature}"
                }

            st.markdown("### 🛠️ 场景与模板配置")
            
            # 2. 改进版：添加自定义模板界面 (修复问题 2)
            col_tmpl1, col_tmpl2 = st.columns([6, 4])
            with col_tmpl1:
                selected_scenario = st.selectbox("📌 当前邮件场景", options=list(st.session_state.email_templates.keys()))
            
            with col_tmpl2:
                st.markdown("<br>", unsafe_allow_html=True)
                with st.popover("➕ 导入/新增自定义模板", use_container_width=True):
                    new_name = st.text_input("1. 模板名称", placeholder="例如：二次催稿")
                    new_content = st.text_area("2. 模板内容", 
                                             placeholder="可用 {name} 代表学者姓名，用 {signature} 代表您的落款", 
                                             height=200)
                    if st.button("💾 确认导入并存入库", use_container_width=True):
                        if new_name and new_content:
                            st.session_state.email_templates[new_name] = new_content
                            st.success(f"模板【{new_name}】已成功导入！")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("请完整填写名称和内容！")

            st.caption("💡 技巧：切换上方场景，下方所有学者的邮件正文将自动更新为对应文案。")
            st.divider()

            # 3. 动态生成区 (修复问题 1)
            st.markdown(f"### 📬 邮件预览：{selected_scenario}")
            
            # 获取当前选中的模板原始文案
            base_template = st.session_state.email_templates[selected_scenario]
            
            for index, row in success_df.iterrows():
                name, email = row['学者姓名'], row['提取邮箱']
                
                with st.expander(f"👤 发送给：{name} ({email})"):
                    # 实时合成落款
                    user_real_name = st.session_state.get('real_name', '陈希然')
                    user_dept_name = st.session_state.get('dept_name', 'Review Of Education')
                    signature = f"\n\nBest regards,\n{user_real_name}\nEditorial Board, {user_dept_name}"
                    
                    # 核心修复点：将占位符替换为真实内容
                    # 这里的 personalized_body 是根据当前选中的 selected_scenario 实时计算的
                    personalized_body = base_template.replace("{name}", str(name)).replace("{signature}", signature)
                    
                    # 标题自动联动
                    subj_val = f"[{selected_scenario}] Academic Communication - {name}"
                    
                    # 注意：这里给 text_area 加了一个带有 selected_scenario 的 key
                    # 这能确保切换场景时，文本框内容会强制“跳跃”到新模板
                    subj = st.text_input("邮件主题", value=subj_val, key=f"s_{index}_{selected_scenario}")
                    body = st.text_area("邮件正文", value=personalized_body, height=300, key=f"b_{index}_{selected_scenario}")
                    
                    # 唤起链接
                    link = f"mailto:{email}?subject={urllib.parse.quote(subj)}&body={urllib.parse.quote(body)}"
                    st.markdown(f'''
                        <a href="{link}" target="_blank">
                            <button style="
                                background-color: #4CAF50; 
                                color: white; 
                                padding: 10px 24px; 
                                border: none; 
                                border-radius: 8px; 
                                font-size: 16px; 
                                font-weight: bold;
                                cursor: pointer;
                                width: 100%;
                                transition: 0.3s;
                            ">📧 唤起本地邮箱发送</button>
                        </a>
                    ''', unsafe_allow_html=True)

# ----------------- 第三层：编辑部资产库 (防错加强版) -----------------
with tab3:
    if not st.session_state.db_url:
        st.info("👈 请先在右上角【必填配置】中绑定您的专属数据库 URL。")
    else:
        st.markdown(f"### 🏛️ {st.session_state.user_name} 的专属云端资产库")
        
        if st.button("🔄 强制同步云端数据"):
            st.rerun()

        db_result = load_from_custom_db(st.session_state.db_url)

        if isinstance(db_result, str):
            st.error(f"❌ 读取失败: {db_result}")
        elif db_result.empty:
            st.info("📭 当前资产库为空，或表头未设置。")
        else:
            # --- 自动对齐列名 (关键修复) ---
            # 清除所有列名的空格，防止因为“所属机构 ”（带空格）导致的报错
            db_result.columns = db_result.columns.str.strip()
            all_cols = db_result.columns.tolist()
            
            st.write("---")
            col_f1, col_f2 = st.columns(2)
            
            # 动态检测“姓名”和“机构”这两列是否存在
            name_col = "学者姓名" if "学者姓名" in all_cols else (all_cols[0] if len(all_cols)>0 else None)
            inst_col = "所属机构" if "所属机构" in all_cols else (all_cols[1] if len(all_cols)>1 else None)

            with col_f1:
                if name_col:
                    db_result['首字母'] = db_result[name_col].apply(lambda x: str(x)[0].upper() if pd.notnull(x) else "#")
                    letter_list = sorted(db_result['首字母'].unique())
                    selected_letter = st.multiselect("🔠 按 A-Z 姓名首字母筛选", options=letter_list)
                else:
                    st.warning("表格中未找到姓名列")

            with col_f2:
                if inst_col:
                    inst_list = sorted(db_result[inst_col].unique())
                    selected_inst = st.multiselect(f"🏫 按【{inst_col}】筛选", options=inst_list)
                else:
                    st.warning("表格中未找到机构列")

            # --- 执行过滤 ---
            filtered_df = db_result.copy()
            if name_col and selected_letter:
                filtered_df = filtered_df[filtered_df['首字母'].isin(selected_letter)]
            if inst_col and selected_inst:
                filtered_df = filtered_df[filtered_df[inst_col].isin(selected_inst)]

            # 展示结果
            st.dataframe(filtered_df, use_container_width=True)