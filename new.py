import streamlit as st
import pandas as pd
from collections import defaultdict

st.set_page_config(page_title="产品配置分析器", layout="wide")

st.title("📊 产品配置差异 & 使用率分析工具")
st.caption("支持叉车/挖机/装载机/平地机/任何产品")

with st.sidebar:
    st.header("📖 使用说明")
    st.markdown("""
    1. 上传 Excel 或 CSV 文件
    2. 选择对应的列
    3. 输入配置分隔符（如 / 或 ,）
    4. 点击「开始分析」
    """)

uploaded = st.file_uploader("📁 上传 Excel 或 CSV 文件", type=["xlsx", "csv"])

if uploaded is None:
    st.info("👆 请先上传数据文件")
    st.stop()

# 根据文件类型读取
try:
    if uploaded.name.endswith("csv"):
        df = pd.read_csv(uploaded)
    else:
        df = pd.read_excel(uploaded, engine="openpyxl")
except Exception as e:
    st.error(f"读取文件失败，请确认文件格式正确。错误信息：{e}")
    st.stop()

st.subheader("📋 数据预览")
st.dataframe(df.head(10))

col_model = st.selectbox("📌 选择「机型」列", df.columns)
col_config = st.selectbox("📝 选择「配置描述」列", df.columns)
col_qty = st.selectbox("📊 选择「数量/销量」列", df.columns)
split_char = st.text_input("✂️ 配置分隔符", value="/")

if st.button("🚀 开始分析", type="primary"):
    df_clean = df.copy()
    df_clean[col_qty] = pd.to_numeric(df_clean[col_qty], errors="coerce").fillna(0)
    df_clean = df_clean[df_clean[col_config].notna()]
    df_clean = df_clean[df_clean[col_config].astype(str).str.strip() != ""]
    df_clean = df_clean[df_clean[col_config].astype(str).str.strip() != "#N/A"]

    if len(df_clean) == 0:
        st.error("有效数据为空")
        st.stop()

    df_clean["配置项列表"] = df_clean[col_config].apply(
        lambda x: [item.strip() for item in str(x).split(split_char) if item.strip()]
    )

    results = []
    for model, group in df_clean.groupby(col_model):
        total_qty = group[col_qty].sum()
        if total_qty == 0:
            continue

        config_usage = defaultdict(float)
        config_count = defaultdict(int)

        for _, row in group.iterrows():
            qty = row[col_qty]
            for item in row["配置项列表"]:
                config_usage[item] += qty
                config_count[item] += 1

        config_usage_rate = {k: round(v / total_qty * 100, 2) for k, v in config_usage.items()}

        group["配置组合"] = group["配置项列表"].apply(lambda x: " | ".join(x) if x else "空配置")
        combo_stats = group.groupby("配置组合").agg(销量=(col_qty, "sum")).reset_index().sort_values("销量", ascending=False)

        total_combos = len(group)
        fixed_items = [k for k, v in config_count.items() if v / total_combos >= 0.8]
        variant_items = [k for k in config_usage.keys() if k not in fixed_items]

        suggestions = []
        for item in variant_items:
            rate = config_usage_rate.get(item, 0)
            if rate < 20:
                suggestions.append(f"⚠️ {item} → 使用率 {rate}%，建议取消或选配")
            elif rate < 50:
                suggestions.append(f"📊 {item} → 使用率 {rate}%，建议保留选配")
            else:
                suggestions.append(f"✅ {item} → 使用率 {rate}%，建议标配")

        results.append({
            "机型": model,
            "总销量": int(total_qty),
            "配置组合数": len(combo_stats),
            "固定配置": fixed_items,
            "差异配置": variant_items,
            "配置使用率": config_usage_rate,
            "配置组合明细": combo_stats,
            "建议": suggestions
        })

    st.success(f"✅ 分析完成！共 {len(results)} 个机型")

    for r in results:
        with st.expander(f"🚜 {r['机型']} ｜ 销量 {r['总销量']} ｜ {r['配置组合数']} 种配置"):
            col1, col2 = st.columns(2)
            with col1:
                st.write("**固定配置**")
                for item in r["固定配置"][:10]:
                    st.code(f"• {item}")
            with col2:
                st.write("**差异配置及建议**")
                for s in r["建议"][:8]:
                    if "⚠️" in s:
                        st.warning(s)
                    elif "✅" in s:
                        st.success(s)
                    else:
                        st.info(s)

            st.write("**配置组合销量排名**")
            st.dataframe(r["配置组合明细"])

    export_rows = []
    for r in results:
        for item, rate in r["配置使用率"].items():
            export_rows.append({
                "机型": r["机型"],
                "配置项": item,
                "使用率_%": rate,
                "是否固定": "是" if item in r["固定配置"] else "否"
            })
    export_df = pd.DataFrame(export_rows)
    csv = export_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 下载分析报告 CSV", csv, "配置分析报告.csv", "text/csv")
