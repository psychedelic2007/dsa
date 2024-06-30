import warnings
warnings.simplefilter(action="ignore", category=FutureWarning)
import streamlit as st
from multiapp import MultiApp
from util.pages.home_page import home_page
from util.pages.equilibrium import equilibrium
from util.pages.phase import main
from util.pages.bifurcation import bifurcation_page

app = MultiApp()

app.add_app("Home Page", home_page)
app.add_app("Equilibrium Analysis", equilibrium)
app.add_app("Phase Plane Analysis", main)
app.add_app("Bifurcation Analysis", bifurcation_page)

app.run()

