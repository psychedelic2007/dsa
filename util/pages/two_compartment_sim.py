import streamlit as st
import numpy as np
from scipy.integrate import odeint
import matplotlib.pyplot as plt

def model(y, t, a12_wake, A_wake, A_sleep, a, k):
    sw_cycle = (t % 24 >= 8) & (t % 24 < 24)
    dydt_n = np.zeros((2,))
    dydt_n[0] = A_wake * sw_cycle + A_sleep * (1 - sw_cycle) - (a12_wake * sw_cycle + a * a12_wake * (1 - sw_cycle)) * y[0]
    dydt_n[1] = (a12_wake * sw_cycle + a * a12_wake * (1 - sw_cycle)) * y[0] - k * y[1]
    return dydt_n

def sim():
    st.title("Brain and Plasma Concentration Model")

    # User inputs for parameters
    A_wake = st.number_input("A_wake", value=55.557583)
    A_sleep = st.number_input("A_sleep", value=7.348874)
    a12_wake = st.number_input("a12_wake", value=0.0737390)
    k = st.number_input("k", value=0.346573)
    a = st.number_input("a", value=1.01)

    # Solve the ODE system
    t = np.arange(0.0, 24*100, 0.01)
    y0 = [600, 15.5]
    args = (a12_wake, A_wake, A_sleep, a, k)
    sol = odeint(model, y0, t, args=args)

    # Plot Brain Concentration
    fig1, ax1 = plt.subplots(figsize=(12, 4))
    ax1.plot(t, sol[:, 0], label='Brain', linewidth=2.0)
    ax1.set_xlabel("Time (hr)", fontsize=15)
    ax1.set_ylabel("Brain Concentration", fontsize=15)
    ax1.tick_params(axis='y', labelsize=12)
    ax1.axvline(x=2336, color='gray', linestyle='dashed', linewidth=1)
    ax1.axvline(x=2352, color='gray', linestyle='dashed', linewidth=1)
    ax1.axvline(x=2360, color='gray', linestyle='dashed', linewidth=1)
    ax1.axvline(x=2376, color='gray', linestyle='dashed', linewidth=1)
    ax1.axvline(x=2384, color='gray', linestyle='dashed', linewidth=1)
    ax1.set_xlim(2335, 2396)
    ax1.legend()
    st.pyplot(fig1)

    # Plot Plasma Concentration
    fig2, ax2 = plt.subplots(figsize=(12, 4))
    ax2.plot(t, sol[:, 1], label='Plasma', linewidth=2.0)
    ax2.set_xlabel("Time (hr)", fontsize=15)
    ax2.set_ylabel("Plasma Concentration", fontsize=15)
    ax2.tick_params(axis='y', labelsize=12)
    ax2.axvline(x=2336, color='gray', linestyle='dashed', linewidth=1)
    ax2.axvline(x=2352, color='gray', linestyle='dashed', linewidth=1)
    ax2.axvline(x=2360, color='gray', linestyle='dashed', linewidth=1)
    ax2.axvline(x=2376, color='gray', linestyle='dashed', linewidth=1)
    ax2.axvline(x=2384, color='gray', linestyle='dashed', linewidth=1)
    ax2.set_xlim(2335, 2396)
    ax2.legend()
    st.pyplot(fig2)

if __name__ == "__main__":
    sim()
