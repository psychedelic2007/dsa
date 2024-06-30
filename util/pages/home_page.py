import streamlit as st
from PIL import Image

st.set_page_config(layout="wide")

def home_page():

    st.markdown(
        """
        <style>
        [data-testid="stSidebar"][aria-expanded="true"]{
            background-color: #b388eb;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<h1 style="text-align: center; color: #888888;">'
                '<span style="color: black; font-weight: bold;">D</span>ynamical '
                '<span style="color: black; font-weight: bold;">S</span>ystem '
                '<span style="color: black; font-weight: bold;">A</span>nalysis '
                '</h1>',
                unsafe_allow_html=True)

    st.write("""***""")
