import streamlit as st
import pandas as pd
import numpy as np

# config
st.set_page_config(page_title="test_import_streamlit.py", page_icon=":guardsman:", layout="wide")

# title
st.title("test_import_streamlit_py")
st.write("model imported successfully!")

# elements
st.sidebar.header("Config")
linhas = st.sidebar.slider("Number of lines", min_value=10, max_value=100, value=50)

# generate data
chart_data = pd.DataFrame(
    np.random.randn(linhas, 2),
    columns=['Metric A', 'Metric B']
)

# exibition
st.subheader("Graphic")
st.line_chart(chart_data)

st.subheader("Dataframe")
st.dataframe(chart_data.head()) # show first lines

# button
if st.button("Click me!"):
    st.success("Button clicked!")
