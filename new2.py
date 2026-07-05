import streamlit as st
import pandas as pd
from collections import defaultdict
import difflib

st.set_page_config(page_title="配置对比分析器", layout="wide")

st.title("📊 同机型配置对比 + 差异点识别")
st.caption("自动找出每个机型的「基础型」配置，其他配置只显示差异")

with st.sidebar:
    st.header("📖 使用说明")
    st.markdown("""
    1. 上传 Excel 或 CSV
    2. 选择「机型」「配置描述」「数量」列
    3. 点击分析
    4. 每个机型会显示：
       - 🏆 基础型（销量最多的配置）
       - 📌 其他配置 vs 基础型的差异
    """)

uploaded = st.file_uploader("📁 上传文件", type=["xlsx", "csv"])

if uploaded is None:
    st.info("👆 请上传数据文件")
    st.stop()

if uploaded.name.endswith("csv"):
    df = pd.read_csv(uploaded)
else:
    df = pd.read_excel(uploaded, engine="openpyxl")

st.subheader("📋 数据预览")
st.dataframe(df.head(10))

col_model = st.selectbox("📌 选择「机型」列", df.columns)
col_config = st.selectbox("📝 选择「配置描述」列", df.columns)
col_qty = st.selectbox("📊 选择「数量」列", df.columns)
split_char = st.text_input("✂️ 配置分隔符", value="/")
similarity_threshold = st.slider("🎯 相似度阈值（%），高于此值视为同一基础配置", 50, 95, 70)

if st.button("🚀 开始分析", type="primary"):

    df_clean = df.copy()
    df_clean[col_qty] = pd.to_numeric(df_clean[col_qty], errors="coerce").fillna(0)
    df_clean = df_clean[df_clean[col_config].notna()]
    df_clean = df_clean[df_clean[col_config].astype(str).str.strip() != ""]
    df_clean = df_clean[df_clean[col_config].astype(str).str.strip() != "#N/A"]

    if len(df_clean) == 0:
        st.error("有效数据为空")
        st.stop()

    # 拆分配置为集合
    df_clean["配置项列表"] = df_clean[col_config].apply(
        lambda x: set([item.strip() for item in str(x).split(split_char) if item.strip()])
    )

    all_results = []

    for model, group in df_clean.groupby(col_model):
        if len(group) == 0:
            continue

        # 计算每个配置组合的总销量（按物料号/配置分组）
        group["配置组合_key"] = group["配置项列表"].apply(lambda x: " | ".join(sorted(x)))
        combo_sales = group.groupby("配置组合_key").agg(
            总销量=(col_qty, "sum"),
            物料号=("配置组合_key", lambda x: list(group[group["配置组合_key"] == x.name]["物料号"].values) if "物料号" in group.columns else [])
        ).reset_index()
        combo_sales["配置集合"] = combo_sales["配置组合_key"].apply(lambda x: set(x.split(" | ")))

        # 按销量排序，销量最高的作为基础型
        combo_sales = combo_sales.sort_values("总销量", ascending=False)
        base_combo = combo_sales.iloc[0]
        base_set = base_combo["配置集合"]
        base_key = base_combo["配置组合_key"]
        base_sales = base_combo["总销量"]

        # 计算每个配置组合与基础型的差异
        results = []
        for _, row in combo_sales.iterrows():
            combo_set = row["配置集合"]
            combo_key = row["配置组合_key"]
            sales = row["总销量"]

            # 计算相似度
            if len(base_set) == 0 and len(combo_set) == 0:
                similarity = 100
            elif len(base_set) == 0 or len(combo_set) == 0:
                similarity = 0
            else:
                intersection = len(base_set & combo_set)
                union = len(base_set | combo_set)
                similarity = round(intersection / union * 100, 2) if union > 0 else 0

            # 判断是否为同一基础配置（相似度>=阈值，且销量高的作为基础）
            is_base = (combo_key == base_key)

            # 计算差异
            added = combo_set - base_set  # 比基础型多的配置
            removed = base_set - combo_set  # 比基础型少的配置

            # 格式化差异显示
            diff_parts = []
            for item in added:
                diff_parts.append(f"+{item}")
            for item in removed:
                diff_parts.append(f"-{item}")
            diff_text = " | ".join(diff_parts) if diff_parts else "无差异（基础型）"

            results.append({
                "配置组合": combo_key[:80] + "..." if len(combo_key) > 80 else combo_key,
                "销量": int(sales),
                "销量占比": round(sales / group[col_qty].sum() * 100, 1),
                "与基础型相似度": similarity,
                "是否基础型": "🏆 是" if is_base else "",
                "差异点": diff_text,
                "新增配置": added,
                "减少配置": removed,
                "物料号": row.get("物料号", "")
            })

        # 按销量排序
        results_df = pd.DataFrame(results)

        all_results.append({
            "机型": model,
            "总销量": int(group[col_qty].sum()),
            "基础型配置": base_key[:100] + "..." if len(base_key) > 100 else base_key,
            "基础型销量": int(base_sales),
            "配置数量": len(results),
            "明细": results_df
        })

    # ========== 展示 ==========
    st.success(f"✅ 分析完成！共 {len(all_results)} 个机型")

    for r in all_results:
        with st.expander(f"🚜 {r['机型']} ｜ 总销量 {r['总销量']} ｜ {r['配置数量']} 种配置组合"):

            st.write(f"**🏆 基础型配置**（销量 {r['基础型销量']} 台）")
            st.code(r["基础型配置"])

            st.write("**📌 各配置组合 vs 基础型的差异**")
            display_df = r["明细"][["配置组合", "销量", "销量占比", "与基础型相似度", "是否基础型", "差异点"]]
            st.dataframe(display_df, use_container_width=True)

            # 统计差异项使用率
            st.write("**📊 差异配置项统计（仅列出与基础型不同的配置）**")
            diff_stats = defaultdict(int)
            total_sales = r["总销量"]
            for _, row in r["明细"].iterrows():
                for item in row["新增配置"]:
                    diff_stats[item] += row["销量"]
            for item in diff_stats:
                diff_stats[item] = round(diff_stats[item] / total_sales * 100, 2)

            if diff_stats:
                diff_df = pd.DataFrame(sorted(diff_stats.items(), key=lambda x: x[1], reverse=True), 
                                       columns=["差异配置项", "使用率%"])
                st.dataframe(diff_df, use_container_width=True)
            else:
                st.caption("无差异配置")

    # ========== 导出 ==========
    export_rows = []
    for r in all_results:
        for _, row in r["明细"].iterrows():
            export_rows.append({
                "机型": r["机型"],
                "配置组合": row["配置组合"],
                "销量": row["销量"],
                "与基础型相似度": row["与基础型相似度"],
                "差异点": row["差异点"]
            })

    export_df = pd.DataFrame(export_rows)
    csv = export_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button("📥 下载分析报告 CSV", csv, "配置差异分析报告.csv", "text/csv")
