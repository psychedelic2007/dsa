import warnings
warnings.simplefilter(action="ignore", category=FutureWarning)
import streamlit as st
from multiapp import MultiApp
from util.pages.home_page import home_page
from util.pages.equilibrium import equilibrium
from util.pages.phase import main
from util.pages.two_phase import two_phase
from util.pages.bifurcation import bifurcation_page
from util.pages.two_compartment_sim import sim
from util.pages.three_compartment_sim import sim_three_compartment

app = MultiApp()

app.add_app("Home Page", home_page)
app.add_app("Equilibrium Analysis", equilibrium)
app.add_app("Phase Plane Analysis", main)
app.add_app("2C Phase Analysis", two_phase)
app.add_app("Bifurcation Analysis", bifurcation_page)
app.add_app("Two Compartment Simulation", sim)
app.add_app("Three Compartment Simulation", sim_three_compartment)
app.run()

