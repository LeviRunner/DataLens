import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

# config streamlit
st.set_page_config(page_title="test_import_sqlalchemy.py", layout="wide")

st.title("SQL alchemy")
st.write("model imported successfully!")

# config sqlalchemy  
engine = create_engine('sqlite:///sell.db', echo=False) # In-memory SQLite database

# create data
@st.cache_data
def create_db():
    # initial data
    data_initi = {
        'Product': ['Notebook', 'Mouse', 'Keyboard', 'Monitor', 'Printer', 'Webcam', 'Headset', 'Speaker', 'Microphone', 'Router'],
        'Cantity': [10, 50, 30, 20, 15, 25, 40, 35, 45, 60],
        'Price': [1500.00, 25.00, 45.00, 200.00, 120.00, 80.00, 60.00, 70.00, 90.00, 100.00]
    }
    example_df = pd.DataFrame(data_initi)

    #Generate the Total_Revenue column automatically by Cantity * Price
    example_df['Total_Revenue'] = example_df['Cantity'] * example_df['Price']

    # gravating data in the database
    example_df.to_sql('sales', con=engine, if_exists='replace', index=False)


create_db()

# interation of Pandas + Streamlit
st.subheader("1. direct view data db (SQLite)")

# uding pandas for make query SQL db on SQLAlchemy
df_db = pd.read_sql('SELECT * FROM sales', con=engine)

# exibition table
st.dataframe(df_db, use_container_width=True)

# interation of Pandas + Streamlit
st.subheader("2. Filter and Interation")

min_cant = st.slider("Select minimum quantity", 0, 100, 10)

# Filter dataframe
filter_df = df_db[df_db['Cantity'] >= min_cant]

st.write(f"Were found **{len(filter_df)}** products with a quantity greater than or equal to {min_cant}")

st.dataframe(filter_df, use_container_width=True)

# generation graphic
st.subheader("3. Graphic")

# Streamlit natively understands Pandas DataFrames for creating charts
st.bar_chart(filter_df.set_index('Product')['Total_Revenu'])
