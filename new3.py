import streamlit as st
import pandas as pd
from collections import defaultdict

st.set_page_config(page_title="配置对比分析器", layout="wide")

st.title("📊 同机型配置对比 + 差异点识别（按物料号）")
st.caption("按物料号对比差异，只显示不同点，忽略写法微调")

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
col_material = st.selectbox("📦 选择「物料号」列（选配，用于精确对比）", ["无"] + list(df.columns))
col_config = st.selectbox("📝 选择「配置描述」列", df.columns)
col_qty = st.selectbox("📊 选择「数量」列", df.columns)
split_char = st.text_input("✂️ 配置分隔符", value="/")

if st.button("🚀 开始分析", type="primary"):

    df_clean = df.copy()
    df_clean[col_qty] = pd.to_numeric(df_clean[col_qty], errors="coerce").fillna(0)

    df_clean = df_clean[df_clean[col_config].notna()]
    df_clean = df_clean[df_clean[col_config].astype(str).str.strip() != ""]
    invalid_values = ["#N/A", "#NAME?", "N/A", "nan", "None", "NULL"]
    for val in invalid_values:
        df_clean = df_clean[df_clean[col_config].astype(str).str.strip() != val]

    if len(df_clean) == 0:
        st.error("有效数据为空")
        st.stop()

    df_clean["配置项列表"] = df_clean[col_config].apply(
        lambda x: set([item.strip() for item in str(x).split(split_char) if item.strip()])
    )

    # 如果有物料号，用它作为分组依据
    group_cols = [col_model]
    if col_material != "无":
        group_cols.append(col_material)

    all_results = []

    for model, group in df_clean.groupby(col_model):

        # 按物料号分组（如果有）
        if col_material != "无":
            # 按物料号汇总配置和销量
            material_groups = group.groupby(col_material).agg({
                col_qty: "sum",
                "配置项列表": lambda x: list(x)[0]  # 取第一个配置
            }).reset_index()
            material_groups["配置组合_key"] = material_groups["配置项列表"].apply(lambda x: " | ".join(sorted(x)))
            material_groups["物料号"] = material_groups[col_material]
        else:
            # 没有物料号，按配置组合分组
            group["配置组合_key"] = group["配置项列表"].apply(lambda x: " | ".join(sorted(x)))
            material_groups = group.groupby("配置组合_key").agg({
                col_qty: "sum",
                "配置项列表": lambda x: list(x)[0]
            }).reset_index()
            material_groups["物料号"] = ""

        # 按销量排序
        material_groups = material_groups.sort_values(col_qty, ascending=False)
        base_row = material_groups.iloc[0]
        base_set = base_row["配置项列表"]
        base_key = base_row["配置组合_key"]
        base_material = base_row.get("物料号", "")
        base_sales = base_row[col_qty]

        results = []
        for _, row in material_groups.iterrows():
            combo_set = row["配置项列表"]
            combo_key = row["配置组合_key"]
            sales = row[col_qty]
            material = row.get("物料号", "")

            # 计算相似度
            if len(base_set) == 0 and len(combo_set) == 0:
                similarity = 100
            elif len(base_set) == 0 or len(combo_set) == 0:
                similarity = 0
            else:
                intersection = len(base_set & combo_set)
                union = len(base_set | combo_set)
                similarity = round(intersection / union * 100, 2) if union > 0 else 0

            is_base = (combo_key == base_key)

            added = combo_set - base_set
            removed = base_set - combo_set

            diff_parts = []
            for item in added:
                diff_parts.append(f"+{item}")
            for item in removed:
                diff_parts.append(f"-{item}")
            diff_text = " | ".join(diff_parts) if diff_parts else "无差异（基础型）"

            # 简化差异显示：只显示有变化的配置项
            if diff_parts and len(diff_parts) > 10:
                diff_text = " | ".join(diff_parts[:10]) + f" ... 共{len(diff_parts)}项差异"

            results.append({
                "物料号": material,
                "配置组合": combo_key[:60] + "..." if len(combo_key) > 60 else combo_key,
                "销量": int(sales),
                "销量占比": round(sales / material_groups[col_qty].sum() * 100, 1) if material_groups[col_qty].sum() > 0 else 0,
                "与基础型相似度": similarity,
                "是否基础型": "🏆 是" if is_base else "",
                "差异点": diff_text,
                "新增配置": added,
                "减少配置": removed,
            })

        results_df = pd.DataFrame(results)

        all_results.append({
            "机型": model,
            "总销量": int(material_groups[col_qty].sum()),
            "基础型物料号": base_material,
            "基础型配置": base_key[:100] + "..." if len(base_key) > 100 else base_key,
            "基础型销量": int(base_sales),
            "配置数量": len(results),
            "明细": results_df
        })

    st.success(f"✅ 分析完成！共 {len(all_results)} 个机型")

    for r in all_results:
        with st.expander(f"🚜 {r['机型']} ｜ 总销量 {r['总销量']} ｜ {r['配置数量']} 种配置组合"):

            st.write(f"**🏆 基础型**（物料号：{r['基础型物料号']}，销量 {r['基础型销量']} 台）")

            st.write("**📌 各物料号 vs 基础型的差异**")
            display_df = r["明细"][["物料号", "销量", "销量占比", "与基础型相似度", "是否基础型", "差异点"]]
            st.dataframe(display_df, use_container_width=True)

            # 统计差异项使用率
            st.write("**📊 差异配置项统计**")
            diff_stats = defaultdict(int)
            total_sales = r["总销量"]
            for _, row in r["明细"].iterrows():
                for item in row["新增配置"]:
                    diff_stats[item] += row["销量"]
                for item in row["减少配置"]:
                    diff_stats[item] += row["销量"]

            for item in diff_stats:
                diff_stats[item] = round(diff_stats[item] / total_sales * 100, 2) if total_sales > 0 else 0

            if diff_stats:
                diff_df = pd.DataFrame(sorted(diff_stats.items(), key=lambda x: x[1], reverse=True), 
                                       columns=["差异配置项", "使用率%"])
                st.dataframe(diff_df, use_container_width=True)
            else:
                st.caption("无差异配置")

    export_rows = []
    for r in all_results:
        for _, row in r["明细"].iterrows():
            export_rows.append({
                "机型": r["机型"],
                "物料号": row["物料号"],
                "配置组合": row["配置组合"],
                "销量": row["销量"],
                "与基础型相似度": row["与基础型相似度"],
                "差异点": row["差异点"]
            })

    export_df = pd.DataFrame(export_rows)
    csv = export_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button("📥 下载分析报告 CSV", csv, "配置差异分析报告.csv", "text/csv")
