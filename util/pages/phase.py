import numpy as np
import matplotlib.pyplot as plt
from scipy.integrate import odeint
import streamlit as st

# Parameters
A_wake = 10.000000
A_sleep = 7.213701
a12_wake = 0.490436
k = 0.209977
a = 1.010000
a13_wake = 0.698227
a23_wake = 0.200000

# Equilibrium points
B_wake = A_wake / (a12_wake + a13_wake)
B_sleep = A_sleep / (a * a12_wake + a * a13_wake)
C_wake = (a12_wake * A_wake) / (a23_wake * (a12_wake + a13_wake))
C_sleep = (a * a12_wake * A_sleep) / (a * a23_wake * (a * a12_wake + a * a13_wake))
P_wake = A_wake / k
P_sleep = A_sleep / k

# Function to compute the vector field
def model(y, t, state='wake'):
    if state == 'wake':
        A = A_wake
        a12 = a12_wake
        a13 = a13_wake
        a23 = a23_wake
    else:
        A = A_sleep
        a12 = a * a12_wake
        a13 = a * a13_wake
        a23 = a * a23_wake
    
    dydt = np.zeros((3,))
    dydt[0] = A - (a13 + a12) * y[0]
    dydt[1] = a12 * y[0] - a23 * y[1]
    dydt[2] = a23 * y[1] + a13 * y[0] - k * y[2]
    return dydt

# Function to plot the phase plane
def plot_phase_plane(y1_range, y2_range, state, y1_label, y2_label, equilibrium_y1, equilibrium_y2, title):
    Y1, Y2 = np.meshgrid(y1_range, y2_range)
    U, V = np.zeros(Y1.shape), np.zeros(Y2.shape)
    
    for i in range(Y1.shape[0]):
        for j in range(Y1.shape[1]):
            if y1_label == 'Brain':
                y = [Y1[i, j], 0, Y2[i, j]] if y2_label == 'Plasma' else [Y1[i, j], Y2[i, j], 0]
            elif y1_label == 'CSF':
                y = [0, Y1[i, j], Y2[i, j]]
            dydt = model(y, 0, state=state)
            U[i, j] = dydt[0] if y1_label == 'Brain' else dydt[1]
            V[i, j] = dydt[2] if y2_label == 'Plasma' else dydt[1]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.quiver(Y1, Y2, U, V, width=0.002, color='r' if state == 'wake' else 'b')
    ax.plot(equilibrium_y1, equilibrium_y2, 'ro' if state == 'wake' else 'bo', markersize=8, label=f'Equilibrium {state.capitalize()}')
    ax.set_title(title)
    ax.set_xlabel(f'{y1_label} Concentration')
    ax.set_ylabel(f'{y2_label} Concentration')
    ax.legend()
    
    return fig

# Streamlit App
def main():
    st.title("Interactive Phase Plane Plot")
    
    # Sidebar controls
    state = st.sidebar.radio("State", ('wake', 'sleep'), index=0)
    y1_label = st.sidebar.selectbox("Y1 Axis", ('Brain', 'CSF'))
    y2_label = st.sidebar.selectbox("Y2 Axis", ('CSF', 'Plasma'))

    # User input for axes ranges
    y1_min = st.sidebar.number_input(f"{y1_label} Min", value=-10.0)
    y1_max = st.sidebar.number_input(f"{y1_label} Max", value=20.0)
    y2_min = st.sidebar.number_input(f"{y2_label} Min", value=-10.0 if y2_label == 'CSF' else 0.0)
    y2_max = st.sidebar.number_input(f"{y2_label} Max", value=60.0)

    # Range for plotting
    y1_range = np.linspace(y1_min, y1_max, 20)
    y2_range = np.linspace(y2_min, y2_max, 20)
    
    # Plot phase plane
    fig = plot_phase_plane(y1_range, y2_range, state, y1_label, y2_label,
                           B_wake if state == 'wake' else B_sleep, C_wake if state == 'wake' else C_sleep,
                           f"Phase Plane Plot ({y1_label} vs {y2_label}, {state.capitalize()} State)")
    
    st.pyplot(fig)
    
if __name__ == '__main__':
    main()

