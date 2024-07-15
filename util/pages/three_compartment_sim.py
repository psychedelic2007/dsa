import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
from scipy.integrate import odeint

def model(y, t, A_wake, A_sleep, a12_wake, k, a, a13_wake, a23_wake):
    sw_cycle = (t % 24 >= 8) & (t % 24 < 24)
    dydt_n = np.zeros((3,))
    B, C, P = y
    dydt_n[0] = A_wake * sw_cycle + (A_sleep * (1 - sw_cycle)) - (a13_wake * sw_cycle + a * a13_wake * (1 - sw_cycle) + a12_wake * sw_cycle + a * a12_wake * (1 - sw_cycle)) * B
    dydt_n[1] = (a12_wake * sw_cycle + a * a12_wake * (1 - sw_cycle)) * B - (a23_wake * sw_cycle + a * a23_wake * (1 - sw_cycle)) * C
    dydt_n[2] = (a23_wake * sw_cycle + a * a23_wake * (1 - sw_cycle)) * C + (a13_wake * sw_cycle + a * a13_wake * (1 - sw_cycle)) * B - k * P
    return dydt_n

def sim_three_compartment():
    st.title("Three-Compartment Model: Brain, CSF, and Plasma Concentrations")

    # User inputs for parameters
    A_wake = st.number_input("A_wake", value=59.935858)
    A_sleep = st.number_input("A_sleep", value=7.443667)
    a12_wake = st.number_input("a12_wake", value=0.346573)
    k = st.number_input("k", value=0.346573)
    a = st.number_input("a", value=1.01)
    a13_wake = st.number_input("a13_wake", value=0.1)
    a23_wake = st.number_input("a23_wake", value=0.057762)

    # Solve the ODE system
    t = np.arange(0.0, 24 * 100, 0.01)
    y0 = [600, 600, 15]
    args = (A_wake, A_sleep, a12_wake, k, a, a13_wake, a23_wake)
    sol = odeint(model, y0, t, args=args)

    # Create subplots
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 15), sharex=True)

    # Plot Brain Concentration
    ax1.plot(t, sol[:, 0], label='Brain', linewidth=2.0)
    ax1.set_xlabel("Time (hr)", fontsize=15)
    ax1.set_ylabel("Brain Concentration", fontsize=15)
    ax1.tick_params(axis='y', labelsize=12)
    ax1.legend()

    # Plot CSF Concentration
    ax2.plot(t, sol[:, 1], label='CSF', linewidth=2.0)
    ax2.set_xlabel("Time (hr)", fontsize=15)
    ax2.set_ylabel("CSF Concentration", fontsize=15)
    ax2.tick_params(axis='y', labelsize=12)
    ax2.legend()

    # Plot Plasma Concentration
    ax3.plot(t, sol[:, 2], label='Plasma', linewidth=2.0)
    ax3.set_xlabel("Time (hr)", fontsize=15)
    ax3.set_ylabel("Plasma Concentration", fontsize=15)
    ax3.tick_params(axis='y', labelsize=12)
    ax3.legend()

    # Add vertical lines and set x-axis limits
    for ax in [ax1, ax2, ax3]:
        ax.axvline(x=2336, color='gray', linestyle='dashed', linewidth=1)
        ax.axvline(x=2352, color='gray', linestyle='dashed', linewidth=1)
        ax.axvline(x=2360, color='gray', linestyle='dashed', linewidth=1)
        ax.axvline(x=2376, color='gray', linestyle='dashed', linewidth=1)
        ax.axvline(x=2384, color='gray', linestyle='dashed', linewidth=1)

    plt.xlim(2336, 2400)
    fig.tight_layout()

    st.pyplot(fig)

if __name__ == "__main__":
    sim_three_compartment()
