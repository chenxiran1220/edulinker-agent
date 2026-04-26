import streamlit as st
import pandas as pd
import requests
import re
import time
import urllib.parse
import json

# 设置网页信息
st.set_page_config(page_title="EduLinker", page_icon="🎓", layout="wide")

# ==========================================
# 核心搜索代码 (希然要求的：100%不动)
# ==========================================
def search_scholar_email(name, institution, api_key):
    url = "https://google.serper.dev/search"
    query = urllib.parse.quote(f"{name} {institution} email")
    headers = {'X-API-KEY': api_key}
    try:
        response = requests.get(url + f"?q={query}", headers=headers)
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
# 云端读写函数 (增加稳定性)
# ==========================================
def save_to_custom_db(url, data_dict):
    """向用户提供的 Google Script URL 发送数据"""
    try:
        requests.post(url, data=json.dumps(data_dict), timeout=10)
    except Exception as e:
        st.error(f"云端写入失败，请检查数据库 URL: {str(e)}")

def load_from_custom_db(url):
    """从用户提供的 Google Script URL 读取数据"""
    try:
        response = requests.get(url, timeout=10)
        # 防止权限没设好导致获取到一堆 HTML 网页代码
        if "<html" in response.text.lower():
            st.error("云端读取失败：权限错误。请确保 Apps Script 部署时的权限是 'Anyone' (任何人)。")
            return pd.DataFrame()
            
        raw_data = response.json()
        if len(raw_data) > 1:
            return pd.DataFrame(raw_data[1:], columns=raw_data[0]) # 第一行为表头
        return pd.DataFrame()
    except Exception as e:
        st.error(f"无法连接到数据库: {str(e)}")
        return pd.DataFrame()

# ==========================================
# 状态初始化
# ==========================================
if 'api_key' not in st.session_state: st.session_state.api_key = ""
if 'db_url' not in st.session_state: st.session_state.db_url = ""
if 'user_name' not in st.session_state: st.session_state.user_name = "未认证用户"
if 'search_results' not in st.session_state: st.session_state.search_results = None

# ==========================================
# 页面 UI: 问题 1 & 2 (极简标题 + 右上角合并配置)
# ==========================================
st.markdown("""
    <style>
    .simple-title { font-size: 3rem; font-weight: bold; margin-bottom: 0px; color: #1e3a8a;}
    .simple-subtitle { font-size: 1.2rem; color: #6b7280; margin-top: 0px; margin-bottom: 30px;}
    </style>
    """, unsafe_allow_html=True)

col_title, col_set = st.columns([7, 3])
with col_title:
    st.markdown('<div class="simple-title">EduLinker</div>', unsafe_allow_html=True)
    st.markdown('<div class="simple-subtitle">Make academic exchange easier</div>', unsafe_allow_html=True)

with col_set:
    with st.popover("⚙️ 必填配置 (使用前需设置)"):
        # 1. 拆分字段并设置正确的示例
        st.session_state.real_name = st.text_input("👤 姓名", 
                                                value=st.session_state.get('real_name', ""), 
                                                placeholder="例如：陈希然")
        
        # 修改点：编辑部示例改为 Review Of Education
        st.session_state.dept_name = st.text_input("🏢 编辑部全称", 
                                                value=st.session_state.get('dept_name', ""), 
                                                placeholder="例如：Review Of Education")
        
        # 自动合成标识符，确保与你后续的“第一层”和“第三层”代码逻辑完全兼容
        st.session_state.user_name = f"{st.session_state.real_name} - {st.session_state.dept_name}"
        
        st.session_state.db_url = st.text_input("🔗 专属数据库 URL", 
                                             value=st.session_state.get('db_url', ""), 
                                             help="贴入你在 Apps Script 得到的 URL")
        
        st.session_state.api_key = st.text_input("🔑 Serper API KEY", 
                                              value=st.session_state.get('api_key', ""), 
                                              type="password")
        
        # 2. 修改点：在末尾增加保存按钮
        st.markdown("---") # 加一条分割线，视觉上更整齐
        if st.button("💾 保存配置信息", use_container_width=True):
            if st.session_state.real_name and st.session_state.dept_name and st.session_state.db_url and st.session_state.api_key:
                st.success(f"配置已保存！欢迎您，来自 {st.session_state.dept_name} 的 {st.session_state.real_name}。")
                # 可以在这里根据需要决定是否运行 st.rerun() 来即时锁定状态
            else:
                st.error("⚠️ 请完整填写所有信息后再点击保存！")

# 页面三层结构
tab1, tab2, tab3 = st.tabs(["📑 第一层：自动寻址", "📧 第二层：邮件撰写", "🏛️ 第三层：编辑部资产库"])

# ----------------- 第一层：自动寻址 (云端缓存省流版 + 抗干扰修复) -----------------
with tab1:
    # 1. 下载模板功能
    template_df = pd.DataFrame({
        "authfull": ["Robert Sternberg", "John Dewey"], 
        "inst_name": ["Cornell University", "Columbia University"], 
        "title": ["Professor", "Researcher"], 
        "status": ["Active", "Active"]
    })
    st.download_button(
        label="📥 下载 CSV 空白名单模板", 
        data=template_df.to_csv(index=False).encode('utf-8-sig'), 
        file_name="EduLinker_Upload_Template.csv", 
        mime="text/csv"
    )
    
    # 🌟 新增的填表说明：明确告知必填项
    st.info("💡 **填表说明**：上传的 CSV 文件中，请务必确保包含 **'authfull' (学者姓名)** 和 **'inst_name' (工作单位/所属机构)** 这两列，否则程序将无法识别。")

    # 2. 上传和按钮逻辑
    uploaded_file = st.file_uploader("📁 请上传包含学者名单的 CSV 文件", type=['csv'])
    
    if uploaded_file and st.button("🚀 开始检索并同步云端"): 
        if not st.session_state.api_key or not st.session_state.db_url:
            st.error("请先在右上角【必填配置】中填写 API Key 和 数据库 URL！")
        else:
            input_df = pd.read_csv(uploaded_file)
            results = []
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            total_scholars = len(input_df)
            
            # 🌟 核心新增：在爬虫开始前，先一次性拉取云端数据库作为“缓存池”
            with st.spinner("正在比对云端资产库，为您节省 API 额度..."):
                db_df = load_from_custom_db(st.session_state.db_url)
                
                # 初始化安全的列名变量
                name_col_db = None
                email_col_db = None
                
                # 清洗列名防报错
                if not isinstance(db_df, str) and not db_df.empty:
                    db_df.columns = [str(c).strip() for c in db_df.columns]
                    all_cols = db_df.columns.tolist()
                    
                    # 动态模糊定位“姓名”和“邮箱”列
                    name_col_db = next((c for c in all_cols if "姓名" in c or "Name" in c), None)
                    email_col_db = next((c for c in all_cols if "邮箱" in c or "email" in c.lower()), None)
                else:
                    db_df = pd.DataFrame() # 如果读取失败，就当空表处理

            for idx, row in input_df.iterrows():
                name, inst = row.get('authfull','未知'), row.get('inst_name','未知')
                status_text.text(f"正在检索 ({idx + 1}/{total_scholars}): {name}")
                
                email = "未找到"
                status = "🔴 需人工核查"
                need_api_call = True  # 默认需要调用爬虫
                
                # 🌟 核心新增：拦截器逻辑（使用动态列名，彻底消灭 KeyError）
                if not db_df.empty and name_col_db and email_col_db:
                    # 在云端库中寻找匹配的学者
                    match = db_df[(db_df[name_col_db] == name) & (db_df[email_col_db] != '未找到') & (db_df[email_col_db].notna())]
                    if not match.empty:
                        email = str(match.iloc[-1][email_col_db]) # 取库里最新的一条记录
                        status = "🔵 数据库调取" # 换成蓝色标志，让你知道省了一次钱！
                        need_api_call = False
                
                # 如果库里没有，才调用真实的爬虫 API
                if need_api_call:
                    email, status = search_scholar_email(name, inst, st.session_state.api_key)
                    
                    # 只有新爬到的有效数据，才同步写入云端
                    if email != "未找到":
                        cloud_data = {
                            "name": name, "institution": inst,
                            "title": row.get('title','Researcher'), "status_val": row.get('status','Active'),
                            "email": email, "status": status,
                            "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                            "owner": st.session_state.user_name
                        }
                        save_to_custom_db(st.session_state.db_url, cloud_data)
                
                # 统一打包结果显示在网页上
                res_item = {
                    "学者姓名": name, "所属机构": inst, 
                    "职位": row.get('title','Researcher'), "学者状态": row.get('status','Active'),
                    "提取邮箱": email, "状态": status
                }
                results.append(res_item)
                
                progress_bar.progress((idx + 1) / total_scholars)
                
            status_text.text("✅ 寻址完成，有效新数据已同步至您的私有云端！")
            st.session_state.search_results = pd.DataFrame(results)
            
    # 展示搜索结果并提供下载按钮
    if st.session_state.search_results is not None:
        st.dataframe(st.session_state.search_results, use_container_width=True)
        csv_data = st.session_state.search_results.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 下载本次搜索结果表格", data=csv_data, file_name="EduLinker_Current_Search.csv", mime="text/csv")

# ----------------- 第二层：邮件撰写 (逻辑完全咬合版) -----------------
with tab2:
    if st.session_state.search_results is None:
        st.info("👈 请先在【第一层】上传名单并完成检索，此处将自动生成联络邮件。")
    else:
        df_results = st.session_state.search_results
        success_df = df_results[df_results['提取邮箱'] != '未找到']
        
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